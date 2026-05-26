"""Django app 設定。"""
from django.apps import AppConfig


class MyappConfig(AppConfig):
    """
    `myapp` 的應用程式設定。

    目前維持最基本設定，主要讓 Django 能正確辨識 app 名稱。
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "myapp"
