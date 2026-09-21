from django.contrib import admin
from .models import TiendaWooCommerce


@admin.register(TiendaWooCommerce)
class TiendaWooCommerceAdmin(admin.ModelAdmin):
    list_display = ("codigo_prefijo", "nombre", "canal_venta", "url", "activa", "sincronizar_stock")
    list_filter = ("activa", "sincronizar_stock")
    search_fields = ("codigo_prefijo", "nombre", "url")
