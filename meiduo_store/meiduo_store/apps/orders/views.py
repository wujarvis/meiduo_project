from decimal import Decimal
from django.shortcuts import render
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from  django_redis import get_redis_connection

from users.models import Address
from goods.models import SKU



# Create your views here.
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