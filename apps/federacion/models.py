import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from apps.base.models import TimeStampedModel

class NodoFederado(TimeStampedModel):
    """
    Directorio de Nodos en la Red Indinopy.
    La MES utiliza este modelo para saber a quién enviarle los webhooks 
    (ej: "El Timelock se venció, el Escrow se liberó") y para validar
    que los requests entrantes vienen de un servidor homologado.
    """
    TIPO_NODO_CHOICES = [
        ("mes", _("Nodo MES (Central/Root)")),
        ("comitente", _("Nodo Comitente (Marca)")),
        ("taller", _("Nodo Tallerista")),
        ("banco", _("Nodo Fiduciario / Banco")),
    ]

    id_nodo = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name=_("ID de Nodo"))
    nombre = models.CharField(max_length=150, verbose_name=_("Nombre / Razón Social del Nodo"))
    tipo_nodo = models.CharField(max_length=20, choices=TIPO_NODO_CHOICES, verbose_name=_("Rol en la Red"))
    url_base = models.URLField(
        verbose_name=_("URL Base del API del Nodo"),
        help_text=_("Ej: https://erp.marcapyme.com.ar/api/v1/federacion")
    )
    clave_publica_nodo = models.CharField(
        max_length=128, 
        blank=True, 
        null=True,
        verbose_name=_("Clave Pública (Ed25519) del Servidor"),
        help_text=_("Para validar la firma de los webhooks que envía este nodo.")
    )
    activo = models.BooleanField(default=True, verbose_name=_("Nodo Activo"))

    class Meta:
        verbose_name = _("Nodo Federado")
        verbose_name_plural = _("Nodos Federados")
        ordering = ["-creado_en"]

    def __str__(self):
        return f"[{self.get_tipo_nodo_display()}] {self.nombre}"


class WebhookLog(TimeStampedModel):
    """
    Registro inmutable de tráfico federado.
    Garantiza el "No Repudio": si un nodo niega haber enviado una e-OP,
    acá queda el payload crudo y su firma criptográfica.
    """
    nodo_origen = models.ForeignKey(NodoFederado, on_delete=models.SET_NULL, null=True, blank=True, related_name="logs_enviados")
    endpoint = models.CharField(max_length=255)
    metodo = models.CharField(max_length=10, default="POST")
    payload_recibido = models.JSONField(verbose_name=_("Payload Crudo Recibido"))
    firma_verificada = models.BooleanField(default=False, verbose_name=_("Firma Válida"))
    ip_origen = models.GenericIPAddressField(null=True, blank=True)
    status_code_devuelto = models.IntegerField(default=200)

    class Meta:
        verbose_name = _("Log de Webhook Federado")
        verbose_name_plural = _("Logs de Webhooks Federados")
        ordering = ["-creado_en"]

    def __str__(self):
        return f"{self.metodo} {self.endpoint} - Valid: {self.firma_verificada}"
