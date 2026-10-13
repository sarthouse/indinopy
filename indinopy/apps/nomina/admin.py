from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from import_export import resources
from .models import Sindicato, Empleado, Licencia, ConceptoLiquidacion, LiquidacionNomina, DetalleLiquidacion

# Defino un Resource específico para los conceptos de AFIP por si queres personalizar algo luego
class ConceptoLiquidacionResource(resources.ModelResource):
    class Meta:
        model = ConceptoLiquidacion
        import_id_fields = ('codigo',) # Clave primaria para actualizar o crear

@admin.register(Sindicato)
class SindicatoAdmin(ImportExportModelAdmin):
    list_display = ('nombre', 'codigo_cct', 'cuota_sindical_pct')

class LicenciaInline(admin.TabularInline):
    model = Licencia
    extra = 0

@admin.register(Empleado)
class EmpleadoAdmin(ImportExportModelAdmin):
    list_display = ('nombre_completo', 'cuil', 'sueldo_basico', 'tipo_contrato', 'fecha_ingreso', 'activo')
    list_filter = ('activo', 'tipo_contrato', 'adherido_fondo_cese', 'sindicato')
    search_fields = ('nombre_completo', 'cuil')
    inlines = [LicenciaInline]

@admin.register(ConceptoLiquidacion)
class ConceptoLiquidacionAdmin(ImportExportModelAdmin):
    resource_class = ConceptoLiquidacionResource
    list_display = ('codigo', 'codigo_afip', 'descripcion', 'tipo', 'porcentaje', 'monto_fijo', 'activo')
    list_filter = ('tipo', 'activo')

class DetalleLiquidacionInline(admin.TabularInline):
    model = DetalleLiquidacion
    extra = 0
    readonly_fields = ('subtotal',)

@admin.register(LiquidacionNomina)
class LiquidacionNominaAdmin(admin.ModelAdmin):
    list_display = ('empleado', 'periodo_mes', 'periodo_anio', 'sueldo_bruto', 'total_retenciones', 'sueldo_neto_pagar')
    list_filter = ('periodo_anio', 'periodo_mes', 'empleado')
    inlines = [DetalleLiquidacionInline]
