from django.apps import AppConfig


class ProduccionConfig(AppConfig):
    name = "apps.produccion"

    def ready(self):
        import apps.produccion.signals
