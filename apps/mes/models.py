import uuid
from decimal import Decimal
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


class PerfilPTF(TimeStampedModel):
    """
    Identidad digital y credencial del Promotor Territorial de Formalización (PTF).
    Emitida por la ComisionCredito del distrito correspondiente.

    El PTF es el auditor de campo que:
    - Verifica físicamente que el trabajo se realizó en el taller declarado.
    - Firma criptográficamente la liberación de los Hitos del Escrow.
    - Su firma se valida contra su clave pública registrada aquí por la MES.

    Hereda el patrón OneToOneField(User) de PerfilCriptografico (apps.base),
    pero agrega los campos institucionales propios del rol PTF.
    """

    ROL_CHOICES = [
        ("ptf_junior", _("PTF Junior (en formación)")),
        ("ptf_senior", _("PTF Senior (habilitado para firmar)")),
        ("ptf_coordinador", _("PTF Coordinador (supervisa zona)")),
    ]

    # Identidad
    usuario = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="perfil_ptf",
        verbose_name=_("Usuario del sistema"),
    )

    # Institución habilitante
    comision = models.ForeignKey(
        ComisionCredito,
        on_delete=models.RESTRICT,
        related_name="ptfs_habilitados",
        verbose_name=_("Comisión que lo habilitó"),
    )
    rol = models.CharField(
        max_length=30,
        choices=ROL_CHOICES,
        default="ptf_junior",
        verbose_name=_("Nivel del PTF"),
    )

    # Identidad Criptográfica (emitida por la MES al homologar)
    clave_publica_ed25519 = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("Clave Pública Ed25519"),
        help_text=_(
            "Generada en el dispositivo del PTF. La MES registra solo la clave PÚBLICA."
        ),
    )
    certificado_mes_json = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Certificado Digital MES"),
        help_text=_(
            "JSON firmado por la MES que acredita la identidad y zona del PTF. "
            "Cualquier nodo puede verificarlo offline con la clave pública de la MES."
        ),
    )

    # Zona de cobertura geográfica (PostGIS)
    zona_cobertura = models.MultiPolygonField(
        srid=4326,
        blank=True,
        null=True,
        verbose_name=_("Zona de Cobertura (Polígono GPS)"),
        help_text=_(
            "Municipios o partidos que el PTF puede auditar. "
            "Las firmas de campo se validan contra este polígono."
        ),
    )
    municipios_texto = models.CharField(
        max_length=500,
        blank=True,
        verbose_name=_("Municipios (referencia legible)"),
        help_text=_("Ej: La Matanza, Merlo, Morón"),
    )

    # Vigencia de la credencial
    fecha_emision_credencial = models.DateField(
        verbose_name=_("Fecha de emisión de credencial"),
    )
    fecha_vencimiento_credencial = models.DateField(
        verbose_name=_("Fecha de vencimiento de credencial"),
        help_text=_("La credencial debe renovarse periódicamente ante la Comisión."),
    )

    # Estado y Reputación
    activo = models.BooleanField(
        default=True,
        verbose_name=_("Activo"),
        help_text=_("Desactivar equivale a revocar la credencial en todos los nodos."),
    )
    ucp_score_ptf = models.IntegerField(
        default=0,
        verbose_name=_("Score UCP del PTF"),
        help_text=_(
            "Reputación del PTF. Sube con auditorías correctas, "
            "baja con auditorías fallidas o colusión detectada (Slashing)."
        ),
    )
    auditorias_realizadas = models.IntegerField(
        default=0,
        verbose_name=_("Auditorías realizadas"),
    )
    auditorias_con_incidencia = models.IntegerField(
        default=0,
        verbose_name=_("Auditorías con incidencia"),
    )

    class Meta:
        verbose_name = _("Perfil PTF")
        verbose_name_plural = _("Perfiles PTF")
        ordering = ["-ucp_score_ptf", "usuario__last_name"]

    def __str__(self):
        return (
            f"PTF {self.usuario.get_full_name() or self.usuario.username} "
            f"[{self.comision.region}] — {self.get_rol_display()}"
        )

    @property
    def credencial_vigente(self):
        """Devuelve True si la credencial no está vencida y el PTF está activo."""
        from django.utils import timezone

        return (
            self.activo and self.fecha_vencimiento_credencial >= timezone.now().date()
        )

    @property
    def tasa_incidencia(self):
        """Porcentaje de auditorías con problemas sobre el total."""
        if self.auditorias_realizadas == 0:
            return 0.0
        return round(
            (self.auditorias_con_incidencia / self.auditorias_realizadas) * 100, 1
        )


class LineaCreditoFDI(TimeStampedModel):
    """
    Control centralizado del cupo de crédito otorgado por la MES a cada Marca (Comitente).
    """

    contacto_marca = models.OneToOneField(
        "contactos.Contacto", on_delete=models.CASCADE, related_name="linea_credito_mes"
    )
    limite_otorgado = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("Límite de Crédito Otorgado (ARS)"),
    )
    deuda_viva = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("Deuda Viva (Saldo Pendiente)"),
    )
    mora_activa = models.BooleanField(
        default=False, verbose_name=_("Mora Activa (Bloqueo)")
    )

    class Meta:
        verbose_name = _("Línea de Crédito FDI")
        verbose_name_plural = _("Líneas de Crédito FDI")

    def __str__(self):
        return f"{self.contacto_marca.nombre} - Cupo: ${self.limite_otorgado}"
