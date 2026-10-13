from django.contrib import admin
from .models import NodoFederado, WebhookLog, NovedadFederada


@admin.register(NodoFederado)
class NodoFederadoAdmin(admin.ModelAdmin):
    list_display = ("nombre", "cuit", "tipo_nodo", "url_base", "activo", "creado_en")
    list_filter = ("tipo_nodo", "activo")
    search_fields = ("nombre", "cuit", "url_base")


@admin.register(WebhookLog)
class WebhookLogAdmin(admin.ModelAdmin):
    list_display = ("endpoint", "metodo", "nodo_origen", "firma_verificada", "status_code_devuelto", "creado_en")
    list_filter = ("firma_verificada", "metodo")
    search_fields = ("endpoint", "ip_origen")
    readonly_fields = ("nodo_origen", "endpoint", "metodo", "payload_recibido", "firma_verificada", "ip_origen", "status_code_devuelto")


@admin.register(NovedadFederada)
class NovedadFederadaAdmin(admin.ModelAdmin):
    list_display = ("nodo_destino", "tipo_evento", "leido", "fecha_lectura", "creado_en")
    list_filter = ("leido", "tipo_evento")
    search_fields = ("nodo_destino__nombre", "tipo_evento")
