from django.contrib import admin
from .models import (
    Receta,
    RecetaInsumo,
    RecetaEtapa,
    OrdenProduccion,
    OPVariacion,
    OPInsumoRequerido,
    OPParteProduccion,
    OPParteProduccionLinea,
    OPEtapaTracking,
    OPEtapaLog,
)


class RecetaInsumoInline(admin.TabularInline):
    model = RecetaInsumo
    extra = 1
    fields = ["insumo", "cantidad", "porcentaje_merma_tolerada", "variantes_destino"]
    filter_horizontal = ["variantes_destino"]


class RecetaEtapaInline(admin.TabularInline):
    model = RecetaEtapa
    extra = 1


@admin.register(Receta)
class RecetaAdmin(admin.ModelAdmin):
    list_display = ["producto_template", "nombre_version", "activa", "creado_en"]
    list_filter = ["activa", "producto_template"]
    search_fields = ["producto_template__nombre", "nombre_version"]
    inlines = [RecetaInsumoInline, RecetaEtapaInline]


class OPVariacionInline(admin.TabularInline):
    model = OPVariacion
    extra = 1
    fields = ["producto", "cantidad", "cantidad_producida", "cantidad_pendiente"]
    readonly_fields = ["cantidad_pendiente"]


class OPInsumoRequeridoInline(admin.TabularInline):
    model = OPInsumoRequerido
    extra = 0
    fields = [
        "insumo",
        "origen",
        "cantidad_teorica",
        "cantidad_consumida_real",
        "alerta_merma_display",
        "costo_facturado_fason",
    ]
    readonly_fields = ["alerta_merma_display"]

    @admin.display(description="Control Merma")
    def alerta_merma_display(self, obj):
        if obj.alerta_desvio_merma:
            return "⚠️ Exceso de Merma (>10%)"
        return "✓ Normal"


class OPEtapaTrackingInline(admin.TabularInline):
    model = OPEtapaTracking
    extra = 0
    fields = [
        "etapa_origen",
        "tallerista_asignado",
        "estado",
        "remito_traslado",
        "remito_retorno",
        "costo_servicio_total",
    ]


class OPParteProduccionInline(admin.TabularInline):
    model = OPParteProduccion
    extra = 0
    fields = ["numero_parte", "fecha", "responsable", "movimiento_terminados"]
    readonly_fields = ["fecha"]


@admin.register(OrdenProduccion)
class OrdenProduccionAdmin(admin.ModelAdmin):
    list_display = [
        "numero",
        "receta",
        "cliente",
        "cantidad_total",
        "cantidad_producida",
        "porcentaje_avance",
        "costo_unitario_display",
        "regimen_juridico",
        "estado",
        "hash_status",
        "fecha",
    ]
    list_filter = ["estado", "subestado", "tipo", "regimen_juridico", "es_sello_buen_diseno", "receta__producto_template"]
    search_fields = ["numero", "uuid_identificador", "hash_seguridad", "cliente__razon_social", "receta__producto_template__nombre"]
    inlines = [OPVariacionInline, OPInsumoRequeridoInline, OPEtapaTrackingInline, OPParteProduccionInline]
    readonly_fields = [
        "uuid_identificador",
        "hash_seguridad",
        "hash_status",
        "porcentaje_avance",
        "costo_total_insumos_teorico",
        "costo_total_insumos_real",
        "costo_total_fason",
        "costo_total_estimado",
        "costo_unitario_par",
        "creado_en",
        "modificado_en",
    ]
    actions = ["sellar_ordenes_seleccionadas"]

    @admin.display(description="Costo/Par")
    def costo_unitario_display(self, obj):
        return f"${obj.costo_unitario_par}"

    @admin.display(description="Seguridad e-OP")
    def hash_status(self, obj):
        if not obj.hash_seguridad:
            return "⏳ Sin sellar"
        if obj.verificar_integridad_hash():
            return "🔒 Sellado Válido"
        return "⚠️ Alterado / Inválido"

    @admin.action(description="Sellar hash criptográfico de e-OP seleccionadas")
    def sellar_ordenes_seleccionadas(self, request, queryset):
        count = 0
        for op in queryset:
            op.sellar_hash_eop()
            count += 1
        self.message_user(request, f"{count} e-OP selladas exitosamente.")


class OPParteProduccionLineaInline(admin.TabularInline):
    model = OPParteProduccionLinea
    extra = 1
    fields = ["variacion", "cantidad", "cantidad_segunda", "cantidad_descarte"]


@admin.register(OPParteProduccion)
class OPParteProduccionAdmin(admin.ModelAdmin):
    list_display = ["numero_parte", "op", "fecha", "responsable", "movimiento_terminados"]
    list_filter = ["op"]
    search_fields = ["numero_parte", "op__numero"]
    inlines = [OPParteProduccionLineaInline]


class OPEtapaLogInline(admin.TabularInline):
    model = OPEtapaLog
    extra = 0
    readonly_fields = ["creado_en", "usuario", "estado_anterior", "estado_nuevo", "observacion"]


@admin.register(OPEtapaTracking)
class OPEtapaTrackingAdmin(admin.ModelAdmin):
    list_display = [
        "op",
        "etapa_origen",
        "tallerista_asignado",
        "estado",
        "remito_traslado",
        "remito_retorno",
        "costo_servicio_total",
    ]
    list_filter = ["estado", "tallerista_asignado"]
    search_fields = ["op__numero", "tallerista_asignado__razon_social"]
    inlines = [OPEtapaLogInline]
