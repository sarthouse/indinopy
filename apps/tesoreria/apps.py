from django.apps import AppConfig


class TesoreriaConfig(AppConfig):
    name = "apps.tesoreria"

    def ready(self):
        import apps.tesoreria.signals
