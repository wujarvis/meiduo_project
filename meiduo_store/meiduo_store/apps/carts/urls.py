from django.conf.urls import url

from . import views


urlpatterns = [
    # 展示购物车页面
    url(r'^carts/$', views.CartsView.as_view(), name='info'),
    # 全选商品
    url(r'^carts/selection', views.CartsSelectedAllView.as_view()),
    # 展示简单购物车
    url('r^carts/simple/', )
]
