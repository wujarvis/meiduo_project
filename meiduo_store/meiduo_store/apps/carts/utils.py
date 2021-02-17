import base64, pickle
from django_redis import get_redis_connection


def merge_carts_cookie_redis(request, response, user):
    # 获取cookie中的购物车数据
    cart_str = request.COOKIES.get('carts')
    if not cart_str:
        return response
    # 将cart_str字符串转换成cart_bytes_str
    cart_bytes_str = cart_str.encode()
    # 将cart_bytes_str字符串转换成bytes类型的字典
    cart_bytes_dict = base64.b64decode(cart_bytes_str)
    # 将cart_bytes_dict转换为真正的字典
    cart_dict = pickle.loads(cart_bytes_dict)

    # 查询cart_dict中的商品
    """cart_dict = {
                    "sku_id1":{
                        "count":"1",
                        "selected":"True"
                    },}"""
    new_cart_dict, new_selected_add, new_selected_rem = {}, [], []
    for sku_id, cookie_dict in cart_dict.items():
        new_cart_dict[sku_id] = cookie_dict['count']

        if cookie_dict['selected']:
            new_selected_add.append(sku_id)  # 勾选的商品
        else:
            new_selected_rem.append(sku_id)  # 未勾选的商品

    # 将new_cart_dict导入redis
    redis_conn = get_redis_connection('carts')
    pl = redis_conn.pipeline()
    pl.hmset('carts_%s' % user.id, new_cart_dict)
    # 将勾选状态导入到redis
    if new_selected_add:
        pl.sadd('selected_%s' % user.id, *new_selected_add)
    if new_selected_rem:
        pl.sadd('selected_%s' % user.id, *new_selected_rem)
    pl.execute()

    # 清除cookie
    response.delete_cookie('carts')

    return response
