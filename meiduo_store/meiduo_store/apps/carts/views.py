from django.shortcuts import render
import json, pickle, base64
from django import http
from django_redis import get_redis_connection

from django.views import View
from goods.models import SKU
from meiduo_store.utils.response_code import RETCODE


# Create your views here.
class CartsView(View):
    """购物车"""

    def post(self, request):
        # 加入购物车
        # 接收参数
        json_dict = json.loads(request.body.decode())
        sku_id = json_dict.get('sku_id')
        count = json_dict.get('count')
        selected = json_dict.get('selected', True)  # 默认为True

        # 校验参数
        if not all([sku_id, count]):
            return http.HttpResponseForbidden('缺少必传的参数')
        try:
            SKU.objects.get(id=sku_id)
        except SKU.DoesNotExist:
            return http.HttpResponseForbidden('sku_id错误')
        try:
            count = int(count)  # 是否是数字
        except Exception as e:
            return http.HttpResponseForbidden('count错误')
        if selected:
            if not isinstance(selected, bool):
                return http.HttpResponseForbidden('selected错误')

        # 判断用户是否登录
        user = request.user
        if user.is_authenticated:  # 用户已登录
            # 用户登录：保存至redis
            redis_conn = get_redis_connection('carts')
            pl = redis_conn.pipeline()
            pl.hincrby('carts_%s' % user.id, sku_id, count)  # 以增量的形式保存商品
            if selected:
                pl.sadd('selected_%s' % user.id, sku_id)  # 保存勾选状态
            pl.execute()
            # 响应结果
            return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK'})
        else:
            # 用户未登录：保存至cookies
            cart_str = request.COOKIES.get('carts')
            if cart_str:
                # 将cart_str字符串转换成cart_bytes_str
                cart_bytes_str = cart_str.encode()
                # 将cart_bytes_str字符串转换成bytes类型的字典
                cart_bytes_dict = base64.b64decode(cart_bytes_str)
                # 将cart_bytes_dict转换为真正的字典
                cart_dict = pickle.loads(cart_bytes_dict)
            else:  # 没有购物车数据
                cart_dict = {}
            # 判断当前要添加的商品在cart_dict中是否已存在
            if sku_id in cart_dict:  # 存在，做增量计算
                """{
                    "sku_id1":{
                        "count":"1",
                        "selected":"True"
                    },}"""
                origin_cart = cart_dict[sku_id]['count']
                count += origin_cart
            cart_dict[sku_id] = {
                'count': count,
                'selected': selected
            }

        # 将字典类型的购物车数据转换为可以存入到cookie的文件
        cart_bytes_dict = pickle.dumps(cart_dict)
        cart_bytes_str = base64.b64encode(cart_bytes_dict)
        cart_str = cart_bytes_str.decode()
        response = http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK'})
        response.set_cookie('carts', cart_str)

        # 响应结果
        return response

    def get(self, request):
        # 展示购物车
        # 展示已登录用户存储在redis中的购物车
        user = request.user
        if user.is_authenticated:
            redis_conn = get_redis_connection('carts')
            redis_cart = redis_conn.hgetall('carts_%s' % user.id)  # bytes类型
            redis_selected = redis_conn.smembers('selected_%s' % user.id)
            cart_dict = {}
            for sku_id, count in redis_cart.items():
                cart_dict[sku_id] = {
                    'count': int(count),  # 将bytes类型数据转换为整型
                    'selected': sku_id in redis_selected  # True or False
                }
        else:
            # 展示未登录用户存储在cookie中的购物车
            cart_str = request.COOKIES.get('carts')
            if cart_str:
                # 将cart_str字符串转换成cart_bytes_str
                cart_bytes_str = cart_str.encode()
                # 将cart_bytes_str字符串转换成bytes类型的字典
                cart_bytes_dict = base64.b64decode(cart_bytes_str)
                # 将cart_bytes_dict转换为真正的字典
                cart_dict = pickle.loads(cart_bytes_dict)
            else:  # 没有购物车数据
                cart_dict = {}
        # 获取字典中所有的key
        sku_ids = cart_dict.keys()
        # 一次查出所有的skus
        skus = SKU.objects.filter(id__in=sku_ids)
        cart_skus = []
        for sku in skus:
            cart_skus.append({
                'id': sku.id,
                'name': sku.name,
                'count': cart_dict.get(sku.id).get('count'),
                'selected': str(cart_dict.get(sku.id).get('selected')),  # 将True，转'True'，方便json解析
                'default_image_url': sku.default_image.url,
                'price': str(sku.price),  # 从Decimal('10.2')中取出'10.2'，方便json解析
                'amount': str(sku.price * cart_dict.get(sku.id).get('count')),
            })
        context = {
            'cart_skus': cart_skus
        }

        # 响应结果
        return render(request, 'cart.html', context=context)
