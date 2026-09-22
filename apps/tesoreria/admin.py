from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from .models import (
    Caja,
    ComprobanteTesoreria,
    MovimientoCaja,
    Cheque,
)


@admin.register(Caja)
class CajaAdmin(SimpleHistoryAdmin):
    list_display = ["nombre", "tipo", "moneda", "saldo_actual", "activa"]
    list_filter = ["tipo", "moneda", "activa"]
    search_fields = ["nombre"]


class MovimientoCajaInline(admin.TabularInline):
    model = MovimientoCaja
    extra = 1


@admin.register(ComprobanteTesoreria)
class ComprobanteTesoreriaAdmin(SimpleHistoryAdmin):
    list_display = [
        "numero",
        "tipo",
        "fecha",
        "contacto",
        "estado",
        "total_ingreso",
        "total_egreso",
    ]
    list_filter = ["tipo", "estado", "fecha"]
    search_fields = ["numero", "contacto__nombre"]
    inlines = [MovimientoCajaInline]
    date_hierarchy = "fecha"


@admin.register(Cheque)
class ChequeAdmin(SimpleHistoryAdmin):
    list_display = [
        "numero",
        "banco",
        "tipo",
        "formato",
        "categoria",
        "monto",
        "fecha_pago",
        "estado",
        "nombre_emisor",
    ]
    list_filter = ["tipo", "formato", "categoria", "estado", "banco", "fecha_pago"]
    search_fields = ["numero", "banco", "cuit_emisor", "nombre_emisor"]
    date_hierarchy = "fecha_pago"
