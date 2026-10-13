from django.contrib import admin
from .models import (
    Categoria,
    UnidadMedida,
    ProductoTemplate,
    Atributo,
    AtributoValor,
    Producto,
    Ubicacion,
    Lote,
    StockQuant,
    MovimientoStock,
    LineaMovimientoStock,
)


@admin.register(UnidadMedida)
class UnidadMedidaAdmin(admin.ModelAdmin):
    list_display = ["nombre", "simbolo", "tipo", "activa"]
    list_filter = ["tipo", "activa"]
    search_fields = ["nombre", "simbolo"]


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ["nombre", "parent"]
    search_fields = ["nombre"]


class AtributoValorInline(admin.TabularInline):
    model = AtributoValor
    extra = 1


@admin.register(Atributo)
class AtributoAdmin(admin.ModelAdmin):
    list_display = ["nombre"]
    inlines = [AtributoValorInline]


@admin.register(ProductoTemplate)
class ProductoTemplateAdmin(admin.ModelAdmin):
    list_display = [
        "nombre",
        "codigo_interno",
        "tipo_producto",
        "unidad_medida",
        "costo",
        "stock_minimo",
        "stock_maximo",
        "estado_stock",
        "activo",
    ]
    list_filter = ["tipo_producto", "tracking", "activo", "categoria"]
    search_fields = ["nombre", "codigo_interno"]

    @admin.display(description="Alerta Stock")
    def estado_stock(self, obj):
        if obj.alerta_stock_minimo:
            return "⚠️ Bajo Mínimo"
        return "✓ OK"


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ["sku", "template", "codigo_barras", "precio_extra"]
    search_fields = ["sku", "codigo_barras", "template__nombre"]
    list_filter = ["template"]
    filter_horizontal = ["valores_atributo"]


@admin.register(Ubicacion)
class UbicacionAdmin(admin.ModelAdmin):
    list_display = ["nombre", "tipo", "contacto", "activa"]
    list_filter = ["tipo", "activa"]
    search_fields = ["nombre", "contacto__razon_social"]


@admin.register(Lote)
class LoteAdmin(admin.ModelAdmin):
    list_display = ["numero", "producto", "referencia_externa"]
    search_fields = ["numero", "producto__sku", "referencia_externa"]


@admin.register(StockQuant)
class StockQuantAdmin(admin.ModelAdmin):
    list_display = ["producto", "ubicacion", "lote", "cantidad_fisica", "cantidad_reservada", "cantidad_disponible"]
    list_filter = ["ubicacion", "producto__template"]
    search_fields = ["producto__sku", "producto__template__nombre", "lote__numero"]
    readonly_fields = ["cantidad_fisica", "cantidad_reservada", "cantidad_disponible"]


class LineaMovimientoStockInline(admin.TabularInline):
    model = LineaMovimientoStock
    extra = 1
    fields = ["producto", "cantidad", "cantidad_hecha", "lote", "ubicacion_origen", "ubicacion_destino", "estado"]


@admin.register(MovimientoStock)
class MovimientoStockAdmin(admin.ModelAdmin):
    list_display = ["numero", "tipo", "contacto", "ubicacion_origen", "ubicacion_destino", "estado", "es_fiscal", "backorder_de", "fecha"]
    list_filter = ["tipo", "estado", "es_fiscal", "ubicacion_origen", "ubicacion_destino"]
    search_fields = ["numero", "documento_origen", "contacto__razon_social"]
    inlines = [LineaMovimientoStockInline]
    readonly_fields = ["creado_en", "modificado_en"]
