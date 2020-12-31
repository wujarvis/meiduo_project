from django.contrib.staticfiles.storage import staticfiles_storage
from django.urls import reverse
from jinja2 import Environment


def jinja2_environment(**options):
    env = Environment(**options)
    env.globals.update(
        {'static': staticfiles_storage.url,  # 获取静态文件的前缀
         'url': reverse}  # 反向解析
    )
    return env
