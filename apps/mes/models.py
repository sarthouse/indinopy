import uuid
from django.contrib.gis.db import models
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
from apps.base.models import TimeStampedModel


class ComisionCredito(TimeStampedModel):
    """
    Cuerpo colegiado de 7 sillas que gobierna el distrito.
    """

    nombre = models.CharField(
        max_length=100, verbose_name=_("Nombre de la Comisión / Distrito")
    )
    region = models.CharField(max_length=100, verbose_name=_("Región / Municipio"))
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("Comisión de Crédito y Riesgo")
        verbose_name_plural = _("Comisiones de Crédito")

    def __str__(self):
        return f"{self.nombre} ({self.region})"


class MiembroComision(TimeStampedModel):
    comision = models.ForeignKey(
        ComisionCredito, on_delete=models.CASCADE, related_name="miembros"
    )
    usuario = models.ForeignKey(User, on_delete=models.RESTRICT)
    rol = models.CharField(
        max_length=50,
        choices=[
            ("presidente", "Presidente (INTI)"),
            ("vocal", "Vocal"),
            ("sindical", "Rep. Sindical"),
            ("marca", "Rep. Marcas"),
        ],
        default="vocal",
    )
    clave_publica_ed25519 = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text="Para firma de dictámenes y vetos",
    )

    class Meta:
        verbose_name = _("Miembro de Comisión")
        verbose_name_plural = _("Miembros de Comisión")

    def __str__(self):
        return f"{self.usuario.get_full_name()} - {self.get_rol_display()}"


class RegistroEOP(TimeStampedModel):
    """
    Copia canónica de la Orden de Producción almacenada en el Nodo Central (MES).
    Es un registro sellado (append-only conceptual) que recibe la MES desde el ERP privado.
    """

    uuid_identificador = models.UUIDField(
        unique=True, editable=False, verbose_name=_("UUID de la e-OP original")
    )
    hash_seguridad = models.CharField(
        max_length=64, verbose_name=_("Hash Original (Payload Canónico)")
    )

    comitente_cuit = models.CharField(
        max_length=20, verbose_name=_("CUIT Comitente (Marca)")
    )
    tallerista_cuit = models.CharField(max_length=20, verbose_name=_("CUIT Tallerista"))

    # Snapshot del Vector de Costos
    monto_total_uci = models.DecimalField(
        max_digits=15, decimal_places=2, verbose_name=_("Monto Total (UCI)")
    )

    fecha_recepcion = models.DateTimeField(auto_now_add=True)
    timelock_vencimiento = models.DateTimeField(
        verbose_name=_("Vencimiento Timelock (48h)"),
        help_text=_(
            "Fecha/Hora en que se gatilla el Silencio Positivo si no hay vetos"
        ),
    )

    estado = models.CharField(
        max_length=30,
        choices=[
            ("en_revision", "En Revisión (Timelock Activo)"),
            ("aprobado_silencio", "Aprobado por Silencio Positivo"),
            ("aprobado_expres", "Aprobación Exprés"),
            ("vetado", "Vetado / Observado"),
            ("en_disputa", "En Disputa (Tribunal)"),
        ],
        default="en_revision",
    )

    class Meta:
        verbose_name = _("Registro e-OP (Nodo MES)")
        verbose_name_plural = _("Registros e-OP (Nodo MES)")

    def __str__(self):
        return f"e-OP {self.uuid_identificador} [{self.get_estado_display()}]"


class ResolucionOP(TimeStampedModel):
    """
    Dictámenes u objeciones técnicas emitidas por miembros de la Comisión
    para frenar el Fast-Track / Silencio Positivo.
    """

    registro_eop = models.ForeignKey(
        RegistroEOP, on_delete=models.CASCADE, related_name="resoluciones"
    )
    miembro = models.ForeignKey(MiembroComision, on_delete=models.RESTRICT)
    es_veto = models.BooleanField(default=False, verbose_name=_("¿Es Veto u Objeción?"))
    fundamento = models.TextField(verbose_name=_("Fundamento Técnico/Legal"))
    firma_digital = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        help_text="Firma criptográfica del miembro",
    )

    class Meta:
        verbose_name = _("Resolución de OP")
        verbose_name_plural = _("Resoluciones de OP")

    def __str__(self):
        tipo = "VETO" if self.es_veto else "APROBACIÓN"
        return f"{tipo} - {self.miembro} sobre {self.registro_eop}"


class AlertaColusion(TimeStampedModel):
    """
    Registro de detección de posibles "Talleres Espejo" (Fragmentación Artificial).
    Generado por el worker de Celery que calcula proximidad espacio-temporal.
    """

    taller_cuit_1 = models.CharField(max_length=20)
    taller_cuit_2 = models.CharField(max_length=20)
    distancia_metros = models.FloatField(verbose_name=_("Distancia entre talleres (m)"))
    diferencia_horas = models.FloatField(
        verbose_name=_("Diferencia de tiempo (h) en recepción de OPs")
    )
    estado_investigacion = models.CharField(
        max_length=20,
        choices=[
            ("pendiente", "Pendiente Inspección PTF"),
            ("falsa_alarma", "Falsa Alarma"),
            ("colusion_confirmada", "Colusión Confirmada"),
        ],
        default="pendiente",
    )

    class Meta:
        verbose_name = _("Alerta de Colusión")
        verbose_name_plural = _("Alertas de Colusión")


class TribunalArbitraje(TimeStampedModel):
    """
    Caso en el Tribunal de Arbitraje de Trinchera (Resolución en 72h).
    """

    registro_eop = models.ForeignKey(
        RegistroEOP, on_delete=models.CASCADE, related_name="casos_arbitraje"
    )
    motivo = models.TextField()
    fecha_limite_laudo = models.DateTimeField(verbose_name=_("Plazo Perentorio (72h)"))
    estado = models.CharField(
        max_length=20,
        choices=[
            ("abierto", "Abierto"),
            ("en_deliberacion", "En Deliberación"),
            ("laudado", "Laudado / Cerrado"),
        ],
        default="abierto",
    )
    resolucion = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = _("Caso de Arbitraje")
        verbose_name_plural = _("Casos de Arbitraje")
