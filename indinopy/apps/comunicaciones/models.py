import uuid
from django.db import models
from django.contrib.contenttypes.fields import GenericRelation
from django.utils.translation import gettext_lazy as _
from apps.base.models import TimeStampedModel


class ComunicacionOficial(TimeStampedModel):
    """
    Documento Maestro Oficial (GDE/DEFE Sectorial) entre Nodos de la Red Federada FIMCA.
    Soporta borradores, emisión oficial con firma Ed25519, comunicaciones individuales y colectivas.
    """
    SECUENCIA_CODIGO = "comunicaciones.oficial"

    TIPO_CHOICES = [
        ("nota_oficial", _("Nota Oficial (NO)")),
        ("cedula_notificacion", _("Cédula de Notificación Electrónica")),
        ("laudo_arbitral", _("Laudo Arbitral Firme")),
        ("resolucion_comision", _("Resolución de Comisión de Crédito")),
        ("intimacion_entrega", _("Intimación de Plazo / Entrega")),
        ("descargo_taller", _("Descargo Técnico de Tallerista")),
        ("circular_sectorial", _("Circular Sectorial Homologada")),
    ]

    ESTADO_DOCUMENTO_CHOICES = [
        ("borrador", _("Borrador (Interno)")),
        ("emitida", _("Emitida Oficialmente (Firmada)")),
        ("archivada", _("Archivada / Concluida")),
        ("anulada", _("Anulada")),
    ]

    ALCANCE_CHOICES = [
        ("individual", _("Individual (1 Destinatario Directo)")),
        ("colectiva_dirigida", _("Colectiva Dirigida (Múltiples Destinatarios TO/CC/CCO)")),
        ("circular_abierta", _("Circular Abierta (Erga Omnes / Toda la Red)")),
    ]

    uuid_identificador = models.UUIDField(
        default=uuid.uuid4, editable=False, unique=True, verbose_name=_("UUID Identificador")
    )
    numero_oficial = models.CharField(
        max_length=60, unique=True, null=True, blank=True,
        verbose_name=_("Número Oficial (GDE Sectorial)"),
        help_text=_("Asignado al firmar y emitir. Ej: NO-2026-00000001-MES-SUR")
    )

    # Identidad Emisora
    cuit_emisor = models.CharField(max_length=20, verbose_name=_("CUIT Emisor"))
    contacto_emisor = models.ForeignKey(
        "contactos.Contacto",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="comunicaciones_emitidas",
        verbose_name=_("Contacto Emisor (Libreta Local)")
    )

    tipo = models.CharField(
        max_length=30, choices=TIPO_CHOICES, default="nota_oficial", verbose_name=_("Tipo de Comunicación")
    )
    alcance = models.CharField(
        max_length=30, choices=ALCANCE_CHOICES, default="individual", verbose_name=_("Alcance de la Cédula")
    )
    estado = models.CharField(
        max_length=20, choices=ESTADO_DOCUMENTO_CHOICES, default="borrador", verbose_name=_("Estado del Documento")
    )

    asunto = models.CharField(max_length=255, verbose_name=_("Asunto / Carátula"))
    cuerpo_contenido = models.TextField(verbose_name=_("Cuerpo del Mensaje Oficial"))
    es_cifrado = models.BooleanField(
        default=False, verbose_name=_("¿Cuerpo Cifrado Asimétricamente (Curve25519)?")
    )

    # Integridad y Trazabilidad Criptográfica
    hash_seguridad_payload = models.CharField(
        max_length=64, blank=True, verbose_name=_("Hash SHA-256 Canónico Público")
    )
    hashes_adjuntos = models.JSONField(
        default=list, blank=True, verbose_name=_("Hashes SHA-256 de Archivos Adjuntos")
    )
    adjuntos = GenericRelation(
        "documentos.DocumentoAdjunto",
        content_type_field="content_type",
        object_id_field="object_id",
        related_query_name="comunicacion_oficial",
    )
    firma_emisor_ed25519 = models.CharField(
        max_length=128, blank=True, null=True, verbose_name=_("Firma Ed25519 del Emisor")
    )

    fecha_emision = models.DateTimeField(null=True, blank=True, verbose_name=_("Fecha de Emisión Oficial"))

    class Meta:
        verbose_name = _("Comunicación Oficial")
        verbose_name_plural = _("Comunicaciones Oficiales")
        ordering = ["-creado_en"]

    def __str__(self):
        identificador = self.numero_oficial or f"Borrador ({str(self.uuid_identificador)[:8]})"
        return f"{identificador} — {self.asunto} [{self.get_estado_display()}]"


class CedulaDestinatario(TimeStampedModel):
    """
    Renglón de notificación individual o colectiva de una Comunicación Oficial.
    Administra la condición de entrega (TO, CC, CCO), acuse fehaciente y cómputo de 48h.
    """
    MODO_RECEPCION_CHOICES = [
        ("principal", _("Destinatario Principal (TO) — Carátula Pública")),
        ("copia_publica", _("En Copia Institucional (CC) — Veedor Abierto")),
        ("copia_oculta", _("En Copia Oculta (CCO) — Reserva de Identidad")),
    ]

    ESTADO_NOTIFICACION_CHOICES = [
        ("pendiente", _("Pendiente de Entrega en Buzón")),
        ("entregada", _("Entregada en Domicilio Electrónico")),
        ("notificada_expresa", _("Notificada Expresa (Acuse Firmado)")),
        ("notificada_tacita", _("Notificada Tácita (Vencimiento 48h de Oficio)")),
        ("rechazada", _("Rechazada")),
    ]

    comunicacion = models.ForeignKey(
        ComunicacionOficial, on_delete=models.CASCADE, related_name="destinatarios",
        verbose_name=_("Comunicación Oficial")
    )
    cuit_destino = models.CharField(max_length=20, verbose_name=_("CUIT Destinatario"))
    contacto_destino = models.ForeignKey(
        "contactos.Contacto",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cedulas_recibidas",
        verbose_name=_("Contacto Destino (Libreta Local)")
    )
    modo_recepcion = models.CharField(
        max_length=20, choices=MODO_RECEPCION_CHOICES, default="principal",
        verbose_name=_("Modo de Notificación (TO / CC / CCO)")
    )

    estado_notificacion = models.CharField(
        max_length=30, choices=ESTADO_NOTIFICACION_CHOICES, default="pendiente",
        verbose_name=_("Estado de la Cédula")
    )

    firma_acuse_recibo = models.CharField(
        max_length=128, blank=True, null=True, verbose_name=_("Firma Ed25519 de Acuse Fehaciente")
    )
    fecha_puesta_disposicion = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Puesta a Disposición en Buzón")
    )
    fecha_notificacion_fehaciente = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Fecha de Notificación Fehaciente")
    )
    fecha_limite_tacita = models.DateTimeField(
        null=True, blank=True, verbose_name=_("Límite para Notificación Tácita (48h)")
    )

    class Meta:
        verbose_name = _("Cédula a Destinatario")
        verbose_name_plural = _("Cédulas a Destinatarios")
        unique_together = ("comunicacion", "cuit_destino")
        ordering = ["modo_recepcion", "-creado_en"]

    def __str__(self):
        return f"{self.comunicacion.numero_oficial or 'Borrador'} -> {self.cuit_destino} ({self.get_modo_recepcion_display()}) [{self.get_estado_notificacion_display()}]"
