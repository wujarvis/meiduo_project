from decimal import Decimal
from django.core.paginator import Paginator, EmptyPage
from django.shortcuts import render
from django.utils import timezone
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django_redis import get_redis_connection
import json
from django import http
from django.db import transaction
import logging

from users.models import Address
from goods.models import SKU
from meiduo_store.utils.views import LoginRequiredJSONMixin
from .models import OrderInfo, OrderGoods
from meiduo_store.utils.response_code import RETCODE
from . import constants

# Create your views here.
# 创建日志生成器
logger = logging.getLogger('django')


class UserOrderInfoView(LoginRequiredMixin, View):
    """展示我的订单"""

    def get(self, request, page_num):
        # 提供我的订单页面
        user = request.user
        # 查询订单
        orders = user.orderinfo_set.all().order_by('-create_time')  # 按时间逆序
        # 遍历所有订单
        for order in orders:
            # 绑定订单状态
            order.status_name = OrderInfo.ORDER_STATUS_CHOICES[order.status - 1][1]
            # 绑定支付方式
            order.pay_method_name = OrderInfo.PAY_METHOD_CHOICES[order.pay_method - 1][1]
            order.sku_list = []
            # 查询订单商品
            order_goods = order.skus.all()
            # 遍历订单商品
            for order_good in order_goods:
                sku = order_good.sku
                sku.count = order_good.count
                sku.amount = sku.price * sku.count
                order.sku_list.append(sku)

        # 分页
        page_num = int(page_num)
        try:
            paginator = Paginator(orders, constants.ORDERS_LIST_LIMIT)
            page_orders = paginator.page(page_num)
            total_page = paginator.num_pages
        except EmptyPage:
            return http.HttpResponseNotFound('订单不存在')

        context = {
            "page_orders": page_orders,
            'total_page': total_page,
            'page_num': page_num,
        }
        return render(request, "user_center_order.html", context)




class OrderSuccessView(LoginRequiredMixin, View):
    """提交订单成功,展示订单页面"""

    def get(self, request):
        order_id = request.GET.get('order_id')
        payment_amount = request.GET.get('payment_amount')
        pay_method = request.GET.get('pay_method')

        context = {
            'order_id': order_id,
            'payment_amount': payment_amount,
            'pay_method': pay_method
        }
        return render(request, 'order_success.html', context)


class OrderCommitView(LoginRequiredJSONMixin, View):
    """订单提交"""

    def post(self, request):
        # 保存订单 信息和订单商品信息
        # 获取当前要保存的订单数据
        json_dict = json.loads(request.body.decode())
        address_id = json_dict.get('address_id')
        pay_method = json_dict.get('pay_method')
        # 校验参数
        if not all([address_id, pay_method]):
            return http.HttpResponseForbidden('缺少必传参数')
        # 判断address_id是否合法
        try:
            address = Address.objects.get(id=address_id)
        except Exception:
            return http.HttpResponseForbidden('参数address_id错误')
        # 校验Pay_method
        if pay_method not in [OrderInfo.PAY_METHODS_ENUM['CASH'], OrderInfo.PAY_METHODS_ENUM['ALIPAY']]:
            return http.HttpResponseForbidden('参数pay_method错误')

        # 开启一个事务
        with transaction.atomic():
            # 创建事务保存点
            save_id = transaction.savepoint()

            try:  # 暴力回滚
                # 获取登录用户
                user = request.user
                # 生成订单编号：年月日时分秒 + user.id
                order_id = timezone.localtime().strftime('%Y%m%d%H%M%S') + ('%09d' % user.id)
                # 保存订单基本信息 OrderInfo（一）
                order = OrderInfo.objects.create(
                    order_id=order_id,
                    user=user,
                    address=address,
                    total_count=0,
                    total_amount=Decimal('0'),
                    freight=Decimal('10.00'),
                    pay_method=pay_method,
                    status=OrderInfo.ORDER_STATUS_ENUM['UNPAID'] if pay_method == OrderInfo.PAY_METHODS_ENUM[
                        'ALIPAY'] else
                    OrderInfo.ORDER_STATUS_ENUM['UNSEND']
                )
                # 从redis读取购物车中被勾选的商品信息
                redis_conn = get_redis_connection('carts')
                redis_cart = redis_conn.hgetall('carts_%s' % user.id)
                selected = redis_conn.smembers('selected_%s' % user.id)
                carts = {}
                for sku_id in selected:
                    carts[int(sku_id)] = int(redis_cart[sku_id])
                sku_ids = carts.keys()

                # 遍历购物车中被勾选的商品信息
                for sku_id in sku_ids:
                    # 每个商品都有多次下单机会，直到库存不足
                    while True:
                        # 查询SKU信息
                        sku = SKU.objects.get(id=sku_id)  # 查询商品信息时，不能出现缓存，所以没有filter(id__in=sku_ids)

                        # 查询原始库存和销量
                        origin_stock, origin_sales = sku.stock, sku.sales

                        # 判断SKU库存
                        sku_count = carts[sku.id]
                        if sku_count > origin_stock:
                            # 库存不足，回滚
                            transaction.savepoint_rollback(save_id)
                            return http.JsonResponse({'code': RETCODE.STOCKERR, 'errmsg': '库存不足'})

                        # # SKU减少库存，增加销量
                        # sku.stock -= sku_count
                        # sku.sales += sku_count
                        # sku.save()

                        # 查询新的库存和销量
                        new_stock = origin_stock - sku_count
                        new_sales = origin_sales + sku_count
                        # 使用乐观锁更新库存和销量
                        result = SKU.objects.filter(id=sku_id, stock=origin_stock).update(stock=new_stock,
                                                                                          sales=new_sales)
                        # 若果在更新数据时，result = 0,表示原始数据变化了，有资源抢夺
                        if result == 0:
                            # 跳过当前下单，继续下单，直到库存不足或result != 0
                            continue

                        # 修改SPU销量
                        sku.spu.sales += sku_count
                        sku.spu.save()

                        # 保存订单商品信息 OrderGoods（多）
                        OrderGoods.objects.create(
                            order=order,
                            sku=sku,
                            count=sku_count,
                            price=sku.price,
                        )

                        # 保存商品订单中总价和总数量
                        order.total_count += sku_count
                        order.total_amount += (sku_count * sku.price)

                        # 下单成功break
                        break

                # 添加邮费和保存订单信息
                order.total_amount += order.freight
                order.save()
            except Exception as e:
                logger.error(e)
                transaction.savepoint_rollback(save_id)
                return http.JsonResponse({'code': RETCODE.DBERR, 'errmsg': '下单失败'})

            # 提交订单成功，提交一次事务
            transaction.savepoint_commit(save_id)

        # 清除购物车中已结算的商品
        pl = redis_conn.pipeline()
        pl.hdel('carts_%s' % user.id, *selected)
        pl.srem('selected_%s' % user.id, *selected)
        pl.execute()

        # 响应提交订单结果
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': '下单成功', 'order_id': order_id})


class OrderSettlementView(LoginRequiredMixin, View):
    """订单视图"""

    def get(self, request):
        # 提供登录用户信息
        user = request.user
        # 查询地址
        try:
            address = Address.objects.filter(user=user)
        except address.DoesNotExist:
            address = None

        # 从redis中查询需要结算的商品
        redis_conn = get_redis_connection('carts')
        pl = redis_conn.pipeline()
        # 从hash查询出全部的商品
        redis_carts = pl.hgetall('carts_%s' % user.id)
        # 从set中查询已勾选的状态
        selected = pl.smembers('selected_%s' % user.id)
        # 筛选已勾选的商品
        new_carts = {}
        for sku_id in selected:
            new_carts[int(sku_id)] = int(redis_carts[sku_id])  # 将bytes类型转化为int

        # 准备初始值
        total_count = 0
        total_amount = Decimal(0.00)

        # 查询商品
        skus = SKU.objects.filter(id__in=new_carts.keys())
        for sku in skus:  # 为商品增加count和amount属性
            sku.count = new_carts[sku.id]
            sku.amount = sku.count * sku.price
            total_count += sku.count
            total_amount += sku.amount
        # 补充运费
        fright = Decimal(10.00)

        # 构建上下文
        context = {
            'address': address,
            'skus': skus,
            'total_count': total_amount,
            'total_amount': total_count,
            'fright': fright,
            'payment_amount': total_amount + fright,
        }
        # 展示订单页面
        return render(request, 'place_order.html', context=context)
