from django.apps import AppConfig


class MoviegameConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "moviegame"

    def ready(self):
        from . import signals
