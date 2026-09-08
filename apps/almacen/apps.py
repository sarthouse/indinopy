from django.apps import AppConfig

class AlmacenConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.almacen'

    def ready(self):
        # Importamos las señales al arrancar la app para que Django las escuche
        import apps.almacen.signals
