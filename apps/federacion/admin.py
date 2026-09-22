from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline
from apps.documentos.models import DocumentoAdjunto
from .models import NodoFederado, WebhookLog, NovedadFederada, ComunicacionOficialFederada, CedulaDestinatario


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


class CedulaDestinatarioInline(admin.TabularInline):
    model = CedulaDestinatario
    extra = 0
    fields = ("cuit_destino", "nodo_destino", "modo_recepcion", "estado_notificacion", "fecha_notificacion_fehaciente", "fecha_limite_tacita")
    readonly_fields = ("fecha_notificacion_fehaciente", "fecha_limite_tacita")


class DocumentoAdjuntoInline(GenericTabularInline):
    model = DocumentoAdjunto
    extra = 0
    fields = ("nombre", "archivo", "mimetype", "tamano", "descripcion")
    readonly_fields = ("mimetype", "tamano")


@admin.register(ComunicacionOficialFederada)
class ComunicacionOficialFederadaAdmin(admin.ModelAdmin):
    list_display = (
        "numero_oficial",
        "tipo",
        "alcance",
        "asunto",
        "cuit_emisor",
        "estado",
        "fecha_emision",
    )
    list_filter = ("tipo", "alcance", "estado", "es_cifrado")
    search_fields = ("numero_oficial", "asunto", "cuit_emisor")
    readonly_fields = (
        "uuid_identificador",
        "hash_seguridad_payload",
        "firma_emisor_ed25519",
        "fecha_emision",
    )
    inlines = [CedulaDestinatarioInline, DocumentoAdjuntoInline]


@admin.register(CedulaDestinatario)
class CedulaDestinatarioAdmin(admin.ModelAdmin):
    list_display = (
        "comunicacion",
        "cuit_destino",
        "modo_recepcion",
        "estado_notificacion",
        "fecha_puesta_disposicion",
        "fecha_notificacion_fehaciente",
    )
    list_filter = ("modo_recepcion", "estado_notificacion")
    search_fields = ("cuit_destino", "comunicacion__numero_oficial", "comunicacion__asunto")
    readonly_fields = (
        "firma_acuse_recibo",
        "fecha_puesta_disposicion",
        "fecha_notificacion_fehaciente",
        "fecha_limite_tacita",
    )

