from django.conf.urls import url

from . import views


urlpatterns = [
    url(r'^carts/$', views.CartsView.as_view(), name='info'),
    url(r'^carts/selection', views.CartsSelectedAllView.as_view()),
]
