from django.db import models
from django.utils import timezone
from django.contrib.contenttypes.fields import GenericRelation
from simple_history.models import HistoricalRecords


class TimeStampedModel(models.Model):
    """
    Clase abstracta que provee campos de auditoría temporal
    creado_en y modificado_en automáticamente a cualquier modelo.
    """

    creado_en = models.DateTimeField(auto_now_add=True, verbose_name="Creado")
    modificado_en = models.DateTimeField(auto_now=True, verbose_name="Modificado")
    history = HistoricalRecords(inherit=True)

    class Meta:
        abstract = True


class DocumentoBase(TimeStampedModel):
    """
    Clase abstracta para documentos comerciales y operativos
    (Remitos, Pedidos, Órdenes de Compra, etc.) que manejan un ciclo de vida con estados.
    """

    ESTADO_CHOICES = [
        ("borrador", "Borrador"),
        ("confirmado", "Confirmado"),
        ("finalizado", "Finalizado"),
        ("cancelado", "Cancelado"),
        ("anulado", "Anulado"),
    ]

    numero = models.CharField(max_length=50, unique=True, verbose_name="Número")
    fecha = models.DateField(default=timezone.now, verbose_name="Fecha")
    estado = models.CharField(
        max_length=20, choices=ESTADO_CHOICES, default="borrador", verbose_name="Estado"
    )
    observaciones = models.TextField(blank=True, verbose_name="Observaciones")
    adjuntos = GenericRelation(
        "documentos.DocumentoAdjunto",
        content_type_field="content_type",
        object_id_field="object_id",
        related_query_name="%(app_label)s_%(class)s",
    )

    class Meta:
        abstract = True
        ordering = ["-fecha", "-numero"]


class Moneda(TimeStampedModel):
    """
    Modelo para monedas (Odoo: res.currency).
    """
    nombre = models.CharField(max_length=50, verbose_name="Nombre de la moneda")
    codigo = models.CharField(max_length=3, unique=True, verbose_name="Código (ISO 4217)")
    simbolo = models.CharField(max_length=10, verbose_name="Símbolo")
    activa = models.BooleanField(default=True, verbose_name="Activa")

    class Meta:
        verbose_name = "Moneda"
        verbose_name_plural = "Monedas"
        ordering = ["codigo"]

    def __str__(self):
        return f"{self.codigo} - {self.nombre} ({self.simbolo})"



