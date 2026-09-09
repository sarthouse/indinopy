from django.db import models
from apps.base.models import TimeStampedModel

class CondicionPago(TimeStampedModel):
    """
    Modelo para condiciones de pago (Odoo: account.payment.term).
    Define el plazo y estructuración financiera de una deuda (ej. 30/60 días).
    """
    nombre = models.CharField(max_length=100, unique=True, verbose_name="Nombre")
    activa = models.BooleanField(default=True, verbose_name="Activa")

    class Meta:
        verbose_name = "Condición de pago"
        verbose_name_plural = "Condiciones de pago"
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class LineaCondicionPago(models.Model):
    """
    Línea de condición de pago (Odoo: account.payment.term.line).
    Permite desglosar un pago en múltiples cuotas o vencimientos.
    """
    TIPO_VALOR_CHOICES = [
        ("porcentaje", "Porcentaje"),
        ("monto_fijo", "Monto Fijo"),
        ("saldo", "Saldo Restante"),
    ]

    condicion_pago = models.ForeignKey(CondicionPago, on_delete=models.CASCADE, related_name="lineas")
    tipo_valor = models.CharField(max_length=20, choices=TIPO_VALOR_CHOICES, default="porcentaje")
    valor = models.DecimalField(max_digits=5, decimal_places=2, default=100.00, help_text="Ej. 50 para 50%")
    dias = models.PositiveIntegerField(default=0, verbose_name="Días de plazo", help_text="Días desde la fecha de factura")

    class Meta:
        verbose_name = "Línea de condición de pago"
        verbose_name_plural = "Líneas de condición de pago"
        ordering = ["dias"]


class Impuesto(TimeStampedModel):
    """
    Modelo para tasas de impuestos, retenciones y percepciones (Odoo: account.tax).
    """
    TIPO_IMPUESTO_CHOICES = [
        ("iva", "IVA"),
        ("retencion_iva", "Retención de IVA"),
        ("retencion_iibb", "Retención de IIBB"),
        ("retencion_ganancias", "Retención de Ganancias"),
        ("percepcion_iva", "Percepción de IVA"),
        ("percepcion_iibb", "Percepción de IIBB"),
        ("otro", "Otro"),
    ]

    APLICACION_CHOICES = [
        ("ventas", "Ventas (Clientes)"),
        ("compras", "Compras (Proveedores)"),
        ("ambas", "Ambas"),
    ]

    nombre = models.CharField(max_length=100, verbose_name="Nombre del impuesto")
    tipo = models.CharField(max_length=30, choices=TIPO_IMPUESTO_CHOICES, default="iva", verbose_name="Tipo de impuesto")
    aplicacion = models.CharField(max_length=20, choices=APLICACION_CHOICES, default="ambas", verbose_name="Aplicación")
    alicuota = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="Alícuota %")
    activo = models.BooleanField(default=True, verbose_name="Activo")

    class Meta:
        verbose_name = "Impuesto / Alícuota"
        verbose_name_plural = "Impuestos y Alícuotas"
        ordering = ["tipo", "alicuota"]

    def __str__(self):
        return f"{self.nombre} ({self.alicuota}%)"
