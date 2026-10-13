from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline
from apps.documentos.models import DocumentoAdjunto
from apps.comunicaciones.models import ComunicacionOficial, CedulaDestinatario


class CedulaDestinatarioInline(admin.TabularInline):
    model = CedulaDestinatario
    extra = 0
    fields = ("cuit_destino", "contacto_destino", "modo_recepcion", "estado_notificacion", "fecha_notificacion_fehaciente", "fecha_limite_tacita")
    readonly_fields = ("fecha_notificacion_fehaciente", "fecha_limite_tacita")


class DocumentoAdjuntoInline(GenericTabularInline):
    model = DocumentoAdjunto
    extra = 0
    fields = ("nombre", "archivo", "mimetype", "tamano", "descripcion")
    readonly_fields = ("mimetype", "tamano")


@admin.register(ComunicacionOficial)
class ComunicacionOficialAdmin(admin.ModelAdmin):
    list_display = (
        "numero_oficial",
        "tipo",
        "alcance",
        "asunto",
        "cuit_emisor",
        "contacto_emisor",
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
        "contacto_destino",
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
