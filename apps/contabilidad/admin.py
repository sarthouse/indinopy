from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from import_export.admin import ImportExportModelAdmin
from import_export import resources
from .models import (
    CondicionPago,
    LineaCondicionPago,
    Impuesto,
    TipoComprobanteAFIP,
    Diario,
    DocumentoDeuda,
    LineaDocumentoDeuda,
    AplicacionPago,
    Cuenta,
    Asiento,
    Apunte,
)

# === IMPORT EXPORT PARA PLAN DE CUENTAS ===
class CuentaResource(resources.ModelResource):
    class Meta:
        model = Cuenta
        import_id_fields = ('codigo',)
        skip_unchanged = True
        report_skipped = False

@admin.register(Cuenta)
class CuentaAdmin(ImportExportModelAdmin):
    resource_class = CuentaResource
    list_display = ('codigo', 'nombre', 'padre', 'tipo', 'naturaleza', 'imputable')
    list_filter = ('tipo', 'naturaleza', 'imputable')
    search_fields = ('codigo', 'nombre')

class ApunteInline(admin.TabularInline):
    model = Apunte
    extra = 0
    readonly_fields = ('cuenta', 'debe', 'haber', 'contacto', 'descripcion_linea')

@admin.register(Asiento)
class AsientoAdmin(admin.ModelAdmin):
    list_display = ('numero', 'fecha', 'diario', 'descripcion', 'estado')
    list_filter = ('estado', 'diario', 'fecha')
    search_fields = ('numero', 'descripcion')
    inlines = [ApunteInline]
    readonly_fields = ('numero', 'estado')


@admin.register(Diario)
class DiarioAdmin(SimpleHistoryAdmin):
    list_display = ("codigo", "nombre", "tipo", "punto_venta_afip", "es_exportacion")
    list_filter = ("tipo", "es_exportacion")
    search_fields = ("codigo", "nombre")


@admin.register(TipoComprobanteAFIP)
class TipoComprobanteAFIPAdmin(ImportExportModelAdmin):
    list_display = (
        "codigo",
        "nombre",
        "letra",
        "clasificacion_interna",
        "es_electronico",
        "es_mipyme_fce",
    )
    list_filter = (
        "letra",
        "clasificacion_interna",
        "es_electronico",
        "es_mipyme_fce",
        "es_exportacion",
    )
    search_fields = ("codigo", "nombre")


class LineaCondicionPagoInline(admin.TabularInline):
    model = LineaCondicionPago
    extra = 1


@admin.register(CondicionPago)
class CondicionPagoAdmin(SimpleHistoryAdmin):
    list_display = ["nombre", "activa"]
    list_filter = ["activa"]
    search_fields = ["nombre"]
    inlines = [LineaCondicionPagoInline]


@admin.register(Impuesto)
class ImpuestoAdmin(SimpleHistoryAdmin):
    list_display = ["nombre", "tipo", "aplicacion", "alicuota", "activo"]
    list_filter = ["tipo", "aplicacion", "activo"]
    search_fields = ["nombre"]


class LineaDocumentoDeudaInline(admin.TabularInline):
    model = LineaDocumentoDeuda
    extra = 1


class AplicacionPagoInline(admin.TabularInline):
    model = AplicacionPago
    extra = 0
    fk_name = "documento_deuda"
    readonly_fields = ("fecha_aplicacion",)


@admin.register(DocumentoDeuda)
class DocumentoDeudaAdmin(SimpleHistoryAdmin):
    list_display = (
        "numero",
        "diario",
        "tipo",
        "contacto",
        "fecha_emision",
        "monto_total",
        "saldo_pendiente_display",
        "estado",
        "afip_cae",
    )
    list_filter = ("diario", "tipo", "estado", "fecha_emision", "tipo_comprobante_afip")
    search_fields = ("numero", "contacto__nombre", "afip_cae")
    inlines = [LineaDocumentoDeudaInline, AplicacionPagoInline]
    date_hierarchy = "fecha_emision"
    readonly_fields = ("afip_cae", "afip_vencimiento_cae", "creado_en", "modificado_en")

    fieldsets = (
        (
            "Datos Generales",
            {
                "fields": (
                    "numero",
                    "diario",
                    "tipo",
                    "tipo_comprobante_afip",
                    "contacto",
                    "orden_produccion",
                    "estado",
                )
            },
        ),
        (
            "Fechas y Pagos",
            {"fields": ("fecha_emision", "fecha_vencimiento", "condicion_pago")},
        ),
        (
            "Montos y Moneda",
            {
                "fields": (
                    "moneda",
                    "tasa_cambio",
                    "monto_neto",
                    "monto_impuestos",
                    "monto_total",
                )
            },
        ),
        ("Fiscal / AFIP", {"fields": ("afip_cae", "afip_vencimiento_cae")}),
        (
            "Auditoría",
            {"fields": ("creado_en", "modificado_en"), "classes": ("collapse",)},
        ),
    )

    @admin.display(description="Saldo Pendiente")
    def saldo_pendiente_display(self, obj):
        return f"${obj.saldo_pendiente}"


@admin.register(AplicacionPago)
class AplicacionPagoAdmin(SimpleHistoryAdmin):
    list_display = (
        "documento_deuda",
        "comprobante_pago",
        "monto_aplicado",
        "fecha_aplicacion",
    )
    search_fields = ("documento_deuda__numero", "comprobante_pago__numero")
    readonly_fields = ("fecha_aplicacion", "creado_en", "modificado_en")
