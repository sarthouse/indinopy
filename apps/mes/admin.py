from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from .models import (
    ComisionCredito,
    MiembroComision,
    RegistroEOP,
    ResolucionOP,
    AlertaColusion,
    TribunalArbitraje,
)


class MiembroComisionInline(admin.TabularInline):
    model = MiembroComision
    extra = 1
    fields = ("usuario", "rol", "clave_publica_ed25519")


@admin.register(ComisionCredito)
class ComisionCreditoAdmin(SimpleHistoryAdmin):
    list_display = ("nombre", "region", "activa", "creado_en")
    list_filter = ("activa", "region")
    search_fields = ("nombre", "region")
    inlines = [MiembroComisionInline]


class ResolucionOPInline(admin.TabularInline):
    model = ResolucionOP
    extra = 0
    readonly_fields = ("creado_en", "firma_digital")


@admin.register(RegistroEOP)
class RegistroEOPAdmin(SimpleHistoryAdmin):
    list_display = (
        "uuid_identificador",
        "tallerista_cuit",
        "comitente_cuit",
        "estado",
        "timelock_vencimiento",
    )
    list_filter = ("estado",)
    search_fields = (
        "uuid_identificador",
        "hash_seguridad",
        "tallerista_cuit",
        "comitente_cuit",
    )
    inlines = [ResolucionOPInline]
    readonly_fields = (
        "uuid_identificador",
        "hash_seguridad",
        "fecha_recepcion",
        "timelock_vencimiento",
        "creado_en",
        "modificado_en",
    )

    fieldsets = (
        (
            "Identidad e-OP",
            {
                "fields": (
                    "uuid_identificador",
                    "hash_seguridad",
                    "comitente_cuit",
                    "tallerista_cuit",
                )
            },
        ),
        ("Finanzas", {"fields": ("monto_total_uci",)}),
        (
            "Timelock y Gobernanza",
            {"fields": ("estado", "fecha_recepcion", "timelock_vencimiento")},
        ),
    )


@admin.register(AlertaColusion)
class AlertaColusionAdmin(SimpleHistoryAdmin):
    list_display = (
        "taller_cuit_1",
        "taller_cuit_2",
        "distancia_metros",
        "diferencia_horas",
        "estado_investigacion",
    )
    list_filter = ("estado_investigacion",)
    search_fields = ("taller_cuit_1", "taller_cuit_2")
    readonly_fields = ("creado_en", "modificado_en")


@admin.register(TribunalArbitraje)
class TribunalArbitrajeAdmin(SimpleHistoryAdmin):
    list_display = ("registro_eop", "estado", "fecha_limite_laudo", "creado_en")
    list_filter = ("estado",)
    search_fields = ("registro_eop__uuid_identificador", "motivo")
    readonly_fields = ("creado_en", "modificado_en")
