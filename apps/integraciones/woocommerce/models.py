from django.db import models
from apps.base.models import TimeStampedModel, ConfiguracionEmpresa


class TiendaWooCommerce(TimeStampedModel):
    """
    Configuración y credenciales de conexión para cada instancia de WooCommerce.
    Pertenece al módulo satélite de integraciones externas y se vincula 1:1 con un CanalVenta.
    """
    empresa = models.ForeignKey(
        ConfiguracionEmpresa,
        on_delete=models.CASCADE,
        related_name="tiendas_woocommerce",
    )
    canal_venta = models.OneToOneField(
        "ventas.CanalVenta",
        on_delete=models.CASCADE,
        related_name="config_woocommerce",
        null=True,
        blank=True,
        help_text="Canal comercial asociado en el core de ventas",
    )
    nombre = models.CharField(max_length=100, unique=True, help_text="Ej: Tienda Oficial B2C")
    codigo_prefijo = models.CharField(max_length=10, unique=True, help_text="Ej: WC-B2C")
    url = models.URLField(help_text="https://mitienda.com")
    consumer_key = models.CharField(max_length=100)
    consumer_secret = models.CharField(max_length=100)
    webhook_secret = models.CharField(max_length=100, blank=True)
    activa = models.BooleanField(default=True)
    sincronizar_stock = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Tienda WooCommerce"
        verbose_name_plural = "Tiendas WooCommerce"
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.codigo_prefijo})"

    @property
    def almacen_origen(self):
        """Retorna el almacén predeterminado configurado en su canal de venta asociado."""
        if self.canal_venta:
            return self.canal_venta.almacen_predeterminado
        return None
