from django.contrib import admin
from .models import CanalVenta, OrdenVenta, LineaOrdenVenta, LineaRecargoOrden, ListaPrecio, ItemListaPrecio


class ItemListaPrecioInline(admin.TabularInline):
    model = ItemListaPrecio
    extra = 1
    fields = ("producto", "precio_unitario", "cantidad_minima", "vigencia_desde", "vigencia_hasta")


@admin.register(ListaPrecio)
class ListaPrecioAdmin(admin.ModelAdmin):
    list_display = ("nombre", "codigo", "moneda", "activa", "creado_en")
    list_filter = ("activa", "moneda")
    search_fields = ("nombre", "codigo")
    inlines = [ItemListaPrecioInline]


class LineaOrdenVentaInline(admin.TabularInline):
    model = LineaOrdenVenta
    extra = 0
    fields = ("producto", "cantidad", "precio_unitario", "subtotal", "descuento", "total_linea", "referencia_linea_externa")


class LineaRecargoOrdenInline(admin.TabularInline):
    model = LineaRecargoOrden
    extra = 0
    fields = ("nombre", "monto", "impuesto")


@admin.register(CanalVenta)
class CanalVentaAdmin(admin.ModelAdmin):
    list_display = ("codigo", "nombre", "tipo", "almacen_predeterminado", "activo")
    list_filter = ("tipo", "activo")
    search_fields = ("codigo", "nombre")


@admin.register(OrdenVenta)
class OrdenVentaAdmin(admin.ModelAdmin):
    list_display = ("numero", "canal", "cliente", "lista_precio", "monto_total", "estado", "enlace_pdf", "fecha", "referencia_externa")
    list_filter = ("canal", "lista_precio", "estado", "fecha")
    search_fields = ("numero", "cliente__nombre", "referencia_externa", "numero_externo")
    inlines = [LineaOrdenVentaInline, LineaRecargoOrdenInline]
    actions = ["confirmar_ordenes_seleccionadas"]

    @admin.display(description="PDF")
    def enlace_pdf(self, obj):
        if not obj.pk:
            return "-"
        from django.urls import reverse
        from django.utils.html import format_html
        url = reverse("ventas:ov_pdf", kwargs={"pk": obj.pk})
        label = "📋 Presupuesto" if obj.estado == "presupuesto" else "📄 Pedido"
        return format_html('<a href="{}" target="_blank" style="font-weight: bold; color: #2563eb;">{}</a>', url, label)

    @admin.action(description="Confirmar órdenes de venta y reservar stock")
    def confirmar_ordenes_seleccionadas(self, request, queryset):
        from .services import VentasService
        count = 0
        for ov in queryset.exclude(estado="confirmado"):
            ov.estado = "confirmado"
            ov.save(update_fields=["estado"])
            VentasService.generar_remito_salida(ov)
            count += 1
        self.message_user(request, f"{count} órdenes confirmadas y remitos de salida generados.")

