from decimal import Decimal
from django.shortcuts import render
from django.utils import timezone
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from  django_redis import get_redis_connection
import json
from django import http


from users.models import Address
from goods.models import SKU
from meiduo_store.utils.views import LoginRequiredJSONMixin
from .models import OrderInfo, OrderGoods
from meiduo_store.utils.response_code import RETCODE



# Create your views here.
class OrderCommitView(LoginRequiredJSONMixin, View):
    """订单提交"""
    def post(self,request):
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
            status=OrderInfo.ORDER_STATUS_ENUM['UNPAID'] if pay_method == OrderInfo.PAY_METHODS_ENUM['ALIPAY'] else
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
            # 查询SKU信息
            sku = SKU.objects.get(id=sku_id)
            # 判断SKU库存
            sku_count = carts[sku.id]
            if sku_count > sku.stock:
                return http.JsonResponse({'code': RETCODE.STOCKERR, 'errmsg': '库存不足'})

            # SKU减少库存，增加销量
            sku.stock -= sku_count
            sku.sales += sku_count
            sku.save()

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

        # 添加邮费和保存订单信息
        order.total_amount += order.freight
        order.save()

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
            sku.amount = sku.count*sku.price
            total_count += sku.count
            total_amount += sku.amount
        # 补充运费
        fright = Decimal(10.00)

        # 构建上下文
        context = {
            'address':address,
            'skus':skus,
            'total_count':total_amount,
            'total_amount':total_count,
            'fright':fright,
            'payment_amount':total_amount + fright,
        }
        # 展示订单页面
        return render(request, 'place_order.html', context=context)