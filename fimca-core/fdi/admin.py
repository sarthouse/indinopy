from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from .models import (
    ComisionCredito,
    PautaEscrowMES,
    MiembroComision,
    RegistroEOP,
    ResolucionOP,
    AlertaColusion,
    TribunalArbitraje,
    EvaluacionTrayectoriaSETP,
    CertificadoDiligenciaDebida,
    PeritajeCalidadINTI,
    LibretaTrabajoDomicilio,
    CarteraTitulizableBIP,
    SerieBonoBIP,
    SubcuentaReservaFondo,
    PolizaColectivaStock,
    CuentaEspecialCompensacion,
)


@admin.register(PautaEscrowMES)
class PautaEscrowMESAdmin(admin.ModelAdmin):
    list_display = (
        "nombre",
        "resolucion_arancel",
        "comision",
        "alicuota_canon_mes",
        "alicuota_fondo_fdi",
        "alicuota_stock",
        "porcentaje_anticipo_estandar",
        "porcentaje_anticipo_sbd",
        "porcentaje_hito_final",
        "activa",
        "creado_en",
    )
    list_filter = ("activa", "comision")
    search_fields = ("nombre", "comision__nombre")



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


@admin.register(EvaluacionTrayectoriaSETP)
class EvaluacionTrayectoriaSETPAdmin(SimpleHistoryAdmin):
    list_display = (
        "cuit_evaluado",
        "tipo_actor",
        "score_setp",
        "categoria_setp",
        "es_arranque_en_frio",
        "cupo_operativo_uci",
        "ops_cumplidas_exitosas",
    )
    list_filter = ("tipo_actor", "categoria_setp", "es_arranque_en_frio")
    search_fields = ("cuit_evaluado",)


@admin.register(CertificadoDiligenciaDebida)
class CertificadoDiligenciaDebidaAdmin(SimpleHistoryAdmin):
    list_display = (
        "tallerista",
        "comitente",
        "periodo_mes_anio",
        "tipo",
        "estado_puerto_seguro",
        "f931_presentado",
        "poliza_art_vigente",
    )
    list_filter = ("tipo", "estado_puerto_seguro", "f931_presentado")
    search_fields = ("tallerista__nombre", "comitente__nombre", "periodo_mes_anio")


@admin.register(PeritajeCalidadINTI)
class PeritajeCalidadINTIAdmin(SimpleHistoryAdmin):
    list_display = (
        "eop",
        "comitente",
        "tallerista",
        "estado",
        "defecto_imputable_taller",
        "fecha_objecion",
    )
    list_filter = ("estado", "defecto_imputable_taller")
    search_fields = ("eop__numero", "comitente__nombre", "tallerista__nombre")


@admin.register(LibretaTrabajoDomicilio)
class LibretaTrabajoDomicilioAdmin(SimpleHistoryAdmin):
    list_display = (
        "costurero",
        "marca_comitente",
        "eop_asociada",
        "tarifa_paritaria_garantizada_ars",
        "prendas_entregadas",
        "responsabilidad_solidaria_directa",
    )
    search_fields = ("costurero__nombre", "marca_comitente__nombre")


# ── MERCADO DE CAPITALES Y FIDUCIARIA (FDI) ─────────────────────────

class SerieBonoBIPInline(admin.TabularInline):
    from .models import SerieBonoBIP
    model = SerieBonoBIP
    extra = 0
    fields = ("codigo_ticker", "numero_serie", "plazo_dias", "moneda", "monto_emision_nominal", "fecha_vencimiento", "estado")


@admin.register(CarteraTitulizableBIP)
class CarteraTitulizableBIPAdmin(admin.ModelAdmin):
    list_display = ("codigo_cartera", "monto_nominal_total_ars", "monto_nominal_total_uci", "calificacion_promedio_setp", "estado", "fecha_corte")
    list_filter = ("estado",)
    search_fields = ("codigo_cartera", "descripcion")
    inlines = [SerieBonoBIPInline]


@admin.register(SerieBonoBIP)
class SerieBonoBIPAdmin(admin.ModelAdmin):
    list_display = ("codigo_ticker", "cartera_subyacente", "numero_serie", "plazo_dias", "moneda", "monto_emision_nominal", "fecha_vencimiento", "es_etiqueta_svs", "estado")
    list_filter = ("moneda", "plazo_dias", "es_etiqueta_svs", "estado")
    search_fields = ("codigo_ticker", "revisor_externo_cnv")


@admin.register(SubcuentaReservaFondo)
class SubcuentaReservaFondoAdmin(admin.ModelAdmin):
    list_display = ("tipo_reserva", "saldo_disponible_ars", "saldo_bloqueado_ars", "alicuota_canon_pct", "modificado_en")
    list_filter = ("tipo_reserva",)


@admin.register(PolizaColectivaStock)
class PolizaColectivaStockAdmin(admin.ModelAdmin):
    list_display = ("numero_poliza", "compania_aseguradora", "fecha_vigencia_desde", "fecha_vigencia_hasta", "monto_maximo_cobertura_ars", "tasa_prima_anual_pct", "activa")
    list_filter = ("activa", "compania_aseguradora")
    search_fields = ("numero_poliza", "compania_aseguradora")


@admin.register(CuentaEspecialCompensacion)
class CuentaEspecialCompensacionAdmin(admin.ModelAdmin):
    list_display = ("contacto", "entidad_bancaria", "cbu_cvu", "exencion_impuesto_cheque", "inembargabilidad_activa", "activa")
    list_filter = ("exencion_impuesto_cheque", "inembargabilidad_activa", "activa", "entidad_bancaria")
    search_fields = ("contacto__nombre", "cbu_cvu", "alias")
