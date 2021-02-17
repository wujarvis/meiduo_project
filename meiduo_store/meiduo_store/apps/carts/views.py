from django.shortcuts import render
import json, pickle, base64
from django import http
from django_redis import get_redis_connection

from django.views import View
from goods.models import SKU
from meiduo_store.utils.response_code import RETCODE


# Create your views here.
class CartsSelectedAllView(View):
    """全选购物车"""

    def put(self, request):
        # 接收参数
        json_dict = json.loads(request.body.decode)
        selected = json_dict.get('selected', True)
        # # 校验参数
        if selected:
            if not isinstance(selected, bool):
                return http.HttpResponseForbidden('参数selected有误')
        # 登录用户全选购物车
        user = request.user
        if user.is_authenticated:
            redis_conn = get_redis_connection('carts')
            pl = redis_conn.pipeline()
            carts = pl.hgetall('carts_%s' % user.id)
            sku_ids = carts.keys()
            # 判断用户是否全选
            if selected:
                pl.sadd('selected_%s' % user.id, *sku_ids)
            else:  # 取消全选
                pl.srem('selected_%s' % user.id, *sku_ids)

            # 响应结果
            return http.JsonResponse({'code':RETCODE.OK, 'errmsg':'OK'})
        else:
            # 未登录用户全选购物车
            response = http.JsonResponse({'code':RETCODE.OK, 'errmsg':'OK'})
            cart_str = request.COOKIES.get('carts')
            if cart_str:
                # 将cart_str字符串转换成cart_bytes_str
                cart_bytes_str = cart_str.encode()
                # 将cart_bytes_str字符串转换成bytes类型的字典
                cart_bytes_dict = base64.b64decode(cart_bytes_str)
                # 将cart_bytes_dict转换为真正的字典
                cart_dict = pickle.loads(cart_bytes_dict)

                for sku_id in cart_dict:
                    cart_dict[sku_id]['selected'] = selected #True/False

                cart_bytes_dict = pickle.dumps(cart_dict)
                cart_bytes_str = base64.b64encode(cart_bytes_dict)
                cart_str = cart_bytes_str.decode()
                response.set_cookie('carts', cart_str)
            return response



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

    def put(self, request):
        # 修改购物车数据，覆盖内容
        # 接收参数
        json_dict = json.loads(request.body.decode())
        sku_id = json_dict.get('sku_id')
        count = json_dict.get('count')
        selected = json_dict.get('selected', True)  # 默认为True

        # 校验参数
        if not all([sku_id, count]):
            return http.HttpResponseForbidden('缺少必传的参数')
        try:
            sku = SKU.objects.get(id=sku_id)
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
            # 用户登录：将修改后的数据保存至redis
            redis_conn = get_redis_connection('carts')
            pl = redis_conn.pipeline()
            pl.hset('carts_%s' % user.id, sku_id, count)  # 以新值覆盖旧值
            if selected:
                pl.sadd('selected_%s' % user.id, sku_id)  # 保存勾选状态
            else:
                pl.srem('selected_%s' % user.id, sku_id)  # 删除勾选状态
            pl.execute()

            # 创建响应对象
            cart_sku = {
                'id': sku_id,
                'count': count,
                'selected': selected,
                'name': sku.name,
                'default_image_url': sku.default_image.url,
                'price': sku.price,
                'amount': sku.price * count,
            }
            # 响应结果
            return http.JsonResponse({'code': RETCODE.OK, 'errmsg': '修改购物车成功', 'cart_sku': cart_sku})
        else:
            # 用户未登录：修改结果保存至cookies
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
            # 由于前端传入的是最终结果，所以覆盖写入
            cart_dict[sku_id] = {
                'count': count,
                'selected': selected
            }
            # 创建响应对象
            cart_sku = {
                'id': sku_id,
                'count': count,
                'selected': selected,
                'name': sku.name,
                'default_image_url': sku.default_image.url,
                'price': sku.price,
                'amount': sku.price * count,
            }
            # 将字典类型的购物车数据转换为可以存入到cookie的文件
            cart_bytes_dict = pickle.dumps(cart_dict)
            cart_bytes_str = base64.b64encode(cart_bytes_dict)
            cart_str = cart_bytes_str.decode()
            response = http.JsonResponse({'code': RETCODE.OK, 'errmsg': '修改购物车成功', 'cart_sku': cart_sku})
            response.set_cookie('carts', cart_str)
            # 响应结果
            return response

    def delete(self, request):
        # 删除购物车中的记录
        # 接收参数
        json_dict = json.loads(request.body.decode())
        sku_id = json_dict.get('sku_id')

        # 判断sku_id是否存在
        try:
            SKU.objects.get(id=sku_id)
        except SKU.DoesNotExist:
            return http.HttpResponseForbidden('商品不存在')

        # 判断用户是否登录
        user = request.user
        if user.is_authenticated:
            # 用户已登录，删除redis购物车
            redis_conn = get_redis_connection('carts')
            pl = redis_conn.pipeline()
            pl.hdel('carts_%s' % user.id, sku_id)  # 删除购物车商品记录
            pl.srem('selected_%s' % user.id, sku_id)  # 删除勾选状态
            pl.execute()

            return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK'})
        else:
            # 用户未登录，删除cookie购物车
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

            response = http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK'})
            if sku_id in cart_dict:
                del cart_dict[sku_id]  # 删除指定的商品
                # 将字典类型的购物车数据转换为可以存入到cookie的文件
                cart_bytes_dict = pickle.dumps(cart_dict)
                cart_bytes_str = base64.b64encode(cart_bytes_dict)
                cart_str = cart_bytes_str.decode()
                response.set_cookie('carts', cart_str)

            return response
