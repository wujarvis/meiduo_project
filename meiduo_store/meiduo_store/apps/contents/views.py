from django.shortcuts import render
from django.views import View
from collections import OrderedDict

from goods.models import GoodsChannelGroup, GoodsChannel, GoodsCategory
# Create your views here.


class IndexView(View):
    """首页广告"""

    def get(self, request):
        """提供首页广告页面"""
        # 查询并展示商品分类
        # 准备商品分类对应的字典
        categories = OrderedDict()
        # 查询所有的商品频道:37个一级类别
        channels = GoodsChannel.objects.order_by('group_id', 'sequence')
        # 遍历所有频道
        for channel in channels:
            # 获取当前频道所在的组
            group_id = channel.group_id
            # 构造基本的数据框架:只有11个组
            if group_id not in categories:
                categories[group_id] = {'channels': [], 'sub_cats': []}

            # 查询当前频道对应的一级类别
            cat1 = channel.category
            # 将cat1添加到channels
            categories[group_id]['channels'].append({
                'id': cat1.id,
                'name': cat1.name,
                'url': channel.url
            })


        return render(request, 'index.html')