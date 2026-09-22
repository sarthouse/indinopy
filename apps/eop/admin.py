from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from .models import ContratoEOP, EOPHitoEscrow, IndiceUCI


class EOPHitoEscrowInline(admin.TabularInline):
    model = EOPHitoEscrow
    extra = 0
    fields = [
        "nombre",
        "porcentaje_tramo",
        "requiere_auditoria_ptf",
        "requiere_verificacion_arca",
        "factura_asociada_arca",
        "estado",
    ]


@admin.register(ContratoEOP)
class ContratoEOPAdmin(SimpleHistoryAdmin):
    list_display = [
        "numero",
        "nodo_mes",
        "ptf_asignado",
        "estado_escrow",
        "es_sello_buen_diseno",
        "fecha_fondeo_escrow",
    ]
    list_filter = ["estado_escrow", "es_sello_buen_diseno"]
    search_fields = ["numero", "uuid_identificador", "nodo_mes"]
    inlines = [EOPHitoEscrowInline]
    readonly_fields = [
        "uuid_identificador",
        "hash_seguridad",
        "merkle_root_bom",
        "creado_en",
        "modificado_en",
    ]


@admin.register(IndiceUCI)
class IndiceUCIAdmin(SimpleHistoryAdmin):
    list_display = ["fecha", "valor_ars"]
    search_fields = ["fecha"]
    ordering = ["-fecha"]
