from django.apps import AppConfig

class InventarioConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.inventario'

    def ready(self):
        # Importamos las señales al arrancar la app para que Django las escuche
        import apps.inventario.signals
