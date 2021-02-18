from django.conf.urls import url

from . import views


urlpatterns = [
    # 展示订单
    url(r'^orders/settlement/$', views.OrderSettlementView.as_view(), name='settlement'),
    # 提交订单
    url(r'^orders/commit/$', views.OrderCommitView.as_view()),

]