from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from .models import (
    Caja,
    ComprobanteTesoreria,
    MovimientoCaja,
    Cheque,
    IndiceUCI,
    ContratoEscrow,
    HitoEscrow,
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


@admin.register(IndiceUCI)
class IndiceUCIAdmin(SimpleHistoryAdmin):
    list_display = ("fecha", "valor_ars")
    search_fields = ("fecha",)
    ordering = ("-fecha",)


class HitoEscrowInline(admin.TabularInline):
    model = HitoEscrow
    extra = 0
    fields = ("nombre", "porcentaje", "estado", "comprobante_pago")


@admin.register(ContratoEscrow)
class ContratoEscrowAdmin(SimpleHistoryAdmin):
    list_display = ("eop_uuid", "monto_total_uci", "estado", "creado_en")
    list_filter = ("estado",)
    search_fields = ("eop_uuid",)
    inlines = [HitoEscrowInline]
    readonly_fields = ("creado_en", "modificado_en")
