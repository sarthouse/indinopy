from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from .models import Moneda, ConfiguracionEmpresa


@admin.register(Moneda)
class MonedaAdmin(SimpleHistoryAdmin):
    list_display = ["codigo", "nombre", "simbolo", "afip_codigo", "activa"]
    list_filter = ["activa"]
    search_fields = ["codigo", "nombre"]


@admin.register(ConfiguracionEmpresa)
class ConfiguracionEmpresaAdmin(SimpleHistoryAdmin):
    list_display = ["razon_social", "cuit", "afip_entorno"]

    fieldsets = (
        (
            "Datos Comerciales",
            {
                "fields": (
                    "razon_social",
                    "nombre_fantasia",
                    "cuit",
                    "direccion",
                    "telefono",
                    "email",
                    "logo",
                )
            },
        ),
        (
            "Facturación Electrónica (AFIP)",
            {
                "fields": (
                    "afip_entorno",
                    "afip_certificado",
                    "afip_clave_privada",
                )
            },
        ),
    )

    def has_add_permission(self, request):
        """Previene que se agreguen más de una configuración (comportamiento Singleton)."""
        if self.model.objects.count() >= 1:
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        """Opcional: Prevenir que borren la única configuración."""
        return False
