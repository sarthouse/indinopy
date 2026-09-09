from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import OrdenCompra, LineaOrdenCompra, TarifaProveedor


@admin.register(TarifaProveedor)
class TarifaProveedorAdmin(admin.ModelAdmin):
    list_display = ["proveedor", "producto", "moneda", "precio", "cantidad_minima", "tiempo_entrega_dias", "vigencia_desde", "vigencia_hasta"]
    list_filter = ["proveedor", "moneda"]
    search_fields = ["proveedor__nombre", "producto__sku", "producto__template__nombre"]

class LineaOrdenCompraInline(admin.TabularInline):
    model = LineaOrdenCompra
    extra = 1
    fields = [
        "producto",
        "descripcion",
        "cantidad",
        "unidad_medida",
        "precio_unitario",
        "impuesto",
        "subtotal_display",
        "cantidad_recibida",
        "cantidad_pendiente_display",
        "cantidad_facturada",
    ]
    readonly_fields = ["subtotal_display", "cantidad_recibida", "cantidad_pendiente_display"]

    @admin.display(description=_("Subtotal"))
    def subtotal_display(self, obj):
        if obj.pk:
            simbolo = obj.orden_compra.moneda.simbolo if (obj.orden_compra and obj.orden_compra.moneda) else "$"
            return f"{simbolo} {obj.subtotal}"
        return "-"

    @admin.display(description=_("Pendiente"))
    def cantidad_pendiente_display(self, obj):
        if obj.pk:
            return f"{obj.cantidad_pendiente}"
        return "-"


@admin.register(OrdenCompra)
class OrdenCompraAdmin(admin.ModelAdmin):
    list_display = [
        "numero",
        "fecha",
        "proveedor",
        "moneda",
        "total_display",
        "estado",
        "badge_recepcion",
        "badge_facturacion",
        "origen_op",
        "fecha_entrega_esperada",
    ]
    list_filter = [
        "estado",
        "moneda",
        "condicion_pago",
        "fecha",
        "proveedor",
    ]
    search_fields = [
        "numero",
        "proveedor__nombre",
        "proveedor__cuil",
        "observaciones",
    ]
    date_hierarchy = "fecha"
    inlines = [LineaOrdenCompraInline]
    readonly_fields = [
        "subtotal_display",
        "total_iva_display",
        "total_display",
        "porcentaje_recibido_display",
        "creado_en",
        "modificado_en",
    ]
    fieldsets = [
        (
            _("Cabecera"),
            {
                "fields": ["numero", "fecha", "proveedor", "estado"],
            },
        ),
        (
            _("Condiciones Comerciales"),
            {
                "fields": [
                    "condicion_pago",
                    "fecha_entrega_esperada",
                    "moneda",
                    "tipo_cambio",
                ],
            },
        ),
        (
            _("Vinculación Productiva y Observaciones"),
            {
                "fields": ["origen_op", "observaciones"],
            },
        ),
        (
            _("Totales y Cumplimiento"),
            {
                "fields": [
                    "subtotal_display",
                    "total_iva_display",
                    "total_display",
                    "porcentaje_recibido_display",
                ],
            },
        ),
        (
            _("Auditoría"),
            {
                "classes": ["collapse"],
                "fields": ["creado_en", "modificado_en"],
            },
        ),
    ]
    actions = [
        "confirmar_ordenes_seleccionadas",
        "cancelar_ordenes_seleccionadas",
        "actualizar_recepciones_seleccionadas",
    ]

    @admin.display(description=_("Total"))
    def total_display(self, obj):
        simbolo = obj.moneda.simbolo if obj.moneda else "$"
        return f"{simbolo} {obj.total:,.2f}"

    @admin.display(description=_("Subtotal"))
    def subtotal_display(self, obj):
        simbolo = obj.moneda.simbolo if obj.moneda else "$"
        return f"{simbolo} {obj.subtotal:,.2f}"

    @admin.display(description=_("IVA Total"))
    def total_iva_display(self, obj):
        simbolo = obj.moneda.simbolo if obj.moneda else "$"
        return f"{simbolo} {obj.total_iva:,.2f}"

    @admin.display(description=_("% Recibido"))
    def porcentaje_recibido_display(self, obj):
        return f"{obj.porcentaje_recibido}% ({obj.cantidad_total_recibida}/{obj.cantidad_total_pedida})"

    @admin.display(description=_("Recepción"))
    def badge_recepcion(self, obj):
        st = obj.estado_recepcion
        if st == "completo":
            return format_html('<span style="color: #10B981; font-weight: bold;">● Completa</span>')
        elif st == "parcial":
            return format_html(
                '<span style="color: #F59E0B; font-weight: bold;">◐ Parcial ({}%)</span>',
                obj.porcentaje_recibido,
            )
        elif st == "pendiente":
            return format_html('<span style="color: #6B7280;">○ Pendiente</span>')
        return "-"

    @admin.display(description=_("Facturación"))
    def badge_facturacion(self, obj):
        st = obj.estado_facturacion
        if st == "completo":
            return format_html('<span style="color: #10B981; font-weight: bold;">● Facturada</span>')
        elif st == "parcial":
            return format_html('<span style="color: #F59E0B; font-weight: bold;">◐ Parcial</span>')
        elif st == "pendiente":
            return format_html('<span style="color: #6B7280;">○ Pendiente</span>')
        return "-"

    @admin.action(description=_("Confirmar órdenes de compra seleccionadas"))
    def confirmar_ordenes_seleccionadas(self, request, queryset):
        count = 0
        for oc in queryset.filter(estado="borrador"):
            oc.estado = "confirmado"
            oc.save()
            count += 1
        self.message_user(request, f"{count} órdenes de compra confirmadas (remitos de recepción generados).")

    @admin.action(description=_("Cancelar órdenes seleccionadas"))
    def cancelar_ordenes_seleccionadas(self, request, queryset):
        count = 0
        for oc in queryset.exclude(estado__in=["finalizado", "cancelado"]):
            oc.estado = "cancelado"
            oc.save()
            count += 1
        self.message_user(request, f"{count} órdenes canceladas.")

    @admin.action(description=_("Recalcular recepciones desde remitos de stock"))
    def actualizar_recepciones_seleccionadas(self, request, queryset):
        count = 0
        for oc in queryset:
            oc.actualizar_cantidades_recibidas()
            count += 1
        self.message_user(request, f"{count} órdenes sincronizadas con remitos de stock.")
