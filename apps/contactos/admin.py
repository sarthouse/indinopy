from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from .models import CategoriaContacto, Tag, Contacto


@admin.register(CategoriaContacto)
class CategoriaContactoAdmin(SimpleHistoryAdmin):
    list_display = ("nombre", "parent")
    search_fields = ("nombre", "descripcion")


@admin.register(Tag)
class TagAdmin(SimpleHistoryAdmin):
    list_display = ("nombre", "color")
    search_fields = ("nombre",)


@admin.register(Contacto)
class ContactoAdmin(SimpleHistoryAdmin):
    list_display = (
        "codigo",
        "nombre",
        "tipo",
        "condicion_iva",
        "es_taller_homologado",
        "ucp_score",
    )
    list_filter = (
        "tipo",
        "condicion_iva",
        "es_taller_homologado",
        "activo",
        "categoria",
        "tags",
    )
    search_fields = ("codigo", "nombre", "cuil", "email")
    readonly_fields = ("creado_en", "modificado_en")

    fieldsets = (
        (
            "Identificación Básica",
            {"fields": ("codigo", "nombre", "tipo", "categoria", "tags", "activo")},
        ),
        ("Datos Fiscales", {"fields": ("cuil", "condicion_iva")}),
        (
            "Contacto y Ubicación",
            {
                "fields": (
                    "contacto_principal",
                    "telefono",
                    "email",
                    "direccion",
                    "ciudad",
                    "provincia",
                    "codigo_postal",
                )
            },
        ),
        (
            "Identidad Protocolo e-OP (RIGI)",
            {
                "fields": (
                    "es_taller_homologado",
                    "ucp_score",
                    "clave_publica_ed25519",
                    "ubicacion_catastral",
                )
            },
        ),
        ("Tesorería", {"fields": ("limite_credito", "cbu_alias")}),
        (
            "Auditoría",
            {
                "fields": ("notas", "creado_en", "modificado_en"),
                "classes": ("collapse",),
            },
        ),
    )
