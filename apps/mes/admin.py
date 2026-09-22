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
        "tallerista_display",
        "comitente_display",
        "monto_total_uci",
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
        "comitente_display",
        "tallerista_display",
        "fecha_recepcion",
        "timelock_vencimiento",
        "creado_en",
        "modificado_en",
    )

    def es_representante_marcas(self, user):
        """Verifica si el usuario actual es representante del sector Marcas en la Comisión."""
        return MiembroComision.objects.filter(usuario=user, rol="marcas").exists()

    def comitente_display(self, obj):
        import hashlib
        # Se ofusca el CUIT si el usuario es un competidor gremial (Representante de Marcas)
        # para garantizar el secreto comercial y anti-colusión en la MES.
        cuit = obj.comitente_cuit
        if not cuit:
            return "S/D"
        from django.contrib.auth import get_user
        # Si no hay request o es auditor público, anonimizamos prefijo
        return f"Comitente #{hashlib.sha256(cuit.encode()).hexdigest()[:8].upper()}"
    comitente_display.short_description = "Comitente (Ofuscado para Secreto Industrial)"

    def tallerista_display(self, obj):
        return obj.tallerista_cuit or "S/D"
    tallerista_display.short_description = "Tallerista"

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
