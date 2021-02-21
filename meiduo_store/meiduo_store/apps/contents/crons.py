import os
from collections import OrderedDict
from django.template import loader
from django.conf import settings

from .models import ContentCategory
from .utils import get_categories


def generate_static_index_html():
    # 首页静态化
    # 查询首页相关数据
    # 查询并展示商品分类
    categories = get_categories()

    # 查询首页广告数据
    # 查询所有的广告类别
    contents = OrderedDict()
    content_categories = ContentCategory.objects.all()
    for content_category in content_categories:
        # 使用广告类别查询出该类别对应的所有的广告内容
        contents[content_category.key] = content_category.content_set.filter(status=True).order_by(
            'sequence')  # 查询出未下架的广告并排序

    # 构造上下文
    context = {
        'categories': categories,
        'contents': contents
    }

    # 获取首页模板文件
    template = loader.get_template('index.html')

    # 渲染首页html字符串
    html_str = template.render(context)

    # 将首页html字符串写入到指定目录，命名'index.html'
    file_path = os.path.join(settings.STATICFILES_DIRS[0], 'index.html')
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(html_str)
