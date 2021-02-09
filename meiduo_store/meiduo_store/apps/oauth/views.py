from django.shortcuts import render
from django.views import View
from QQLoginTool.QQtool import OAuthQQ
from django.conf import settings
from django import http
import logging

from meiduo_mall.utils.response_code import RETCODE
# Create your views here.


# 创建日志输出器
logger = logging.getLogger('django')


class QQAuthUserView(View):
    """处理QQ登录回调：oauth_callback"""

    def get(self, request):
        """处理QQ登录回调的业务逻辑"""

        # 获取code
        code = request.GET.get('code')
        if not code:
            return http.HttpResponseForbidden('获取code失败')

        # 创建工具对象
        oauth = OAuthQQ(client_id=settings.QQ_CLIENT_ID, client_secret=settings.QQ_CLIENT_SECRET,
                            redirect_uri=settings.QQ_REDIRECT_URI)

        try:
            # 使用code获取access_token
            access_token = oauth.get_access_token(code)

            # 使用access_token获取openid
            openid = oauth.get_open_id(access_token)
        except Exception as e:
            logger.error(e)
            return http.HttpResponseServerError('OAuth2.0认证失败')

        # 使用openid判断该QQ用户是否绑定过美多商城的用户
        pass


class QQAuthURLView(View):
    """提供QQ登录扫码页面"""

    def get(self, request):
        # 接收next
        next = request.GET.get('next')

        # 创建工具对象
        oauth = OAuthQQ(client_id=settings.QQ_CLIENT_ID, client_secret=settings.QQ_CLIENT_SECRET, redirect_uri=settings.QQ_REDIRECT_URI, state=next)

        # 生成QQ登录扫码链接地址
        login_url = oauth.get_qq_url()

        # 响应
        return http.JsonResponse({'code': RETCODE.OK, 'errmsg': 'OK', 'login_url': login_url})