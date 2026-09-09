from django.contrib import admin
from .models import CondicionPago, LineaCondicionPago, Impuesto


class LineaCondicionPagoInline(admin.TabularInline):
    model = LineaCondicionPago
    extra = 1

@admin.register(CondicionPago)
class CondicionPagoAdmin(admin.ModelAdmin):
    list_display = ["nombre", "activa"]
    list_filter = ["activa"]
    search_fields = ["nombre"]
    inlines = [LineaCondicionPagoInline]

@admin.register(Impuesto)
class ImpuestoAdmin(admin.ModelAdmin):
    list_display = ["nombre", "tipo", "aplicacion", "alicuota", "activo"]
    list_filter = ["tipo", "aplicacion", "activo"]
    search_fields = ["nombre"]
