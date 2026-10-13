import uuid
from decimal import Decimal
from django.contrib.gis.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from base.models import TimeStampedModel


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


class PautaEscrowMES(TimeStampedModel):
    """
    Parámetros de Política de Escrow dictaminados por la Mesa de Enlace Sectorial (MES).
    Configura los porcentajes oficiales de liberación fiduciaria para e-OPs.
    """
    comision = models.ForeignKey(
        ComisionCredito,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pautas_escrow",
        verbose_name=_("Comisión / Distrito Emisor (Opcional si es Nacional/Universal)"),
    )
    nombre = models.CharField(
        max_length=120,
        default="Pauta Oficial Escrow MES",
        verbose_name=_("Nombre de la Pauta / Resolución"),
    )
    porcentaje_anticipo_estandar = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("35.00"),
        verbose_name=_("Hito Cero Estándar (%)"),
        help_text=_("Porcentaje de anticipo inicial sin certificación especial."),
    )
    porcentaje_anticipo_sbd = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("50.00"),
        verbose_name=_("Hito Cero Sello Buen Diseño (%)"),
        help_text=_("Porcentaje de anticipo para productos homologados con Sello Buen Diseño."),
    )
    porcentaje_hito_final = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("20.00"),
        verbose_name=_("Hito Final Cierre Fiscal (%)"),
        help_text=_("Porcentaje retenido en retención de cierre fiscal hasta constatar CAE en ARCA."),
    )
    # Parámetros Arancelarios Dinámicos FDI/MES (Art. 4° inc. 4 Ley e-OP)
    resolucion_arancel = models.CharField(
        max_length=50,
        default="RES-MES-2026-01",
        verbose_name=_("Resolución / Versión Arancelaria"),
    )
    alicuota_canon_mes = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal("0.0100"),
        verbose_name=_("Canon Institucional MES s/MOD (máx 1.0%)"),
    )
    alicuota_fondo_fdi = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal("0.0050"),
        verbose_name=_("Fondo de Riesgo FDI s/MOD (máx 0.5%)"),
    )
    alicuota_stock = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal("0.0050"),
        verbose_name=_("Alícuota Cobertura de Stock s/BOM (máx 0.5%)"),
    )
    activa = models.BooleanField(
        default=True,
        verbose_name=_("Pauta Activa"),
        help_text=_("Si está activa, se utiliza para calcular los cronogramas de nuevas e-OPs."),
    )

    class Meta:
        verbose_name = _("Pauta de Escrow MES")
        verbose_name_plural = _("Pautas de Escrow MES")
        ordering = ["-activa", "-creado_en"]

    def __str__(self):
        distrito = self.comision.nombre if self.comision else "Universal / Nacional"
        return f"{self.nombre} [{distrito}] (Std: {self.porcentaje_anticipo_estandar}% | SBD: {self.porcentaje_anticipo_sbd}% | Final: {self.porcentaje_hito_final}%)"


class MiembroComision(TimeStampedModel):
    comision = models.ForeignKey(
        ComisionCredito, on_delete=models.CASCADE, related_name="miembros"
    )
    usuario = models.ForeignKey(User, on_delete=models.RESTRICT)
    rol = models.CharField(
        max_length=50,
        choices=[
            ("inti", "Presidente (INTI)"),
            ("sindicato", "Representante Sindical"),
            ("taller_mono", "Representante Talleristas (Monotributo)"),
            ("taller_sas", "Representante Talleristas (SAS)"),
            ("marcas", "Representante Marcas (Comitentes)"),
            ("municipio", "Representante Municipio (Desarrollo Local)"),
            ("fdi", "Representante Fiduciario (FDI/Banco)"),
        ],
        default="inti",
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
    Caso en el Tribunal Arbitral Territorial (Resolución en 72h).
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
        "base.Contacto", on_delete=models.CASCADE, related_name="linea_credito_mes"
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


class VotacionComision(TimeStampedModel):
    """
    Sesión de votación polimórfica de la ComisionCredito.
    Puede usarse para habilitar PTFs, aprobar créditos, sancionar talleres, etc.
    """

    comision = models.ForeignKey(ComisionCredito, on_delete=models.CASCADE)

    # Asunto Polimórfico (El objeto que se está votando: Un Usuario, Una Línea de Crédito, etc.)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    asunto = GenericForeignKey("content_type", "object_id")

    tipo_asunto = models.CharField(
        max_length=50,
        choices=[
            ("habilitacion_ptf", "Habilitación de PTF"),
            ("aprobacion_credito", "Aprobación de Línea de Crédito FDI"),
            ("sancion_taller", "Sanción a Tallerista"),
        ],
    )

    fecha_apertura = models.DateTimeField(auto_now_add=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    estado = models.CharField(
        max_length=20,
        choices=[
            ("abierta", "Abierta"),
            ("aprobada", "Aprobada"),
            ("rechazada", "Rechazada"),
        ],
        default="abierta",
    )

    class Meta:
        verbose_name = _("Votación de Comisión")
        verbose_name_plural = _("Votaciones de Comisión")


class VotoComision(TimeStampedModel):
    votacion = models.ForeignKey(
        VotacionComision, on_delete=models.CASCADE, related_name="votos"
    )
    miembro = models.ForeignKey(MiembroComision, on_delete=models.CASCADE)
    aprueba = models.BooleanField()
    fundamento = models.TextField(blank=True, null=True)
    firma_digital = models.CharField(max_length=128, blank=True, null=True)

    class Meta:
        unique_together = ("votacion", "miembro")
        verbose_name = _("Voto de Comisión")
        verbose_name_plural = _("Votos de Comisión")


class BolsaTrabajo(TimeStampedModel):
    """
    Bolsa de Trabajo Productivo (Talleristas ofreciendo capacidad).
    """

    tallerista = models.OneToOneField(
        "base.Contacto", on_delete=models.CASCADE, related_name="bolsa_trabajo"
    )
    capacidad_mensual_pares = models.IntegerField(default=0)
    maquinas_disponibles = models.JSONField(default=list, blank=True)
    operarios_activos = models.IntegerField(default=1)
    buscando_trabajo = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("Perfil Bolsa de Trabajo")
        verbose_name_plural = _("Perfiles Bolsa de Trabajo")


class Denuncia(TimeStampedModel):
    """
    Portal de Denuncias y Reclamos de la Comunidad Organizada (FIMCA - Addenda II).
    """

    denunciante = models.ForeignKey(
        "base.Contacto",
        on_delete=models.CASCADE,
        related_name="denuncias_realizadas",
    )
    denunciado = models.ForeignKey(
        "base.Contacto",
        on_delete=models.CASCADE,
        related_name="denuncias_recibidas",
    )

    motivo = models.CharField(
        max_length=50,
        choices=[
            ("precio_bajo_convenio", "Precio por debajo del convenio"),
            ("retencion_pagos", "Retención indebida de pagos (Escrow)"),
            (
                "coima_funcionario",
                "Extorsión/Dádiva de Funcionario Público (AFIP/ARCA)",
            ),
            ("amenaza_rescision", "Amenaza de rescisión de contratos"),
            ("colusion_marca", "Colusión o Simulación por parte de la Marca"),
        ],
    )
    descripcion = models.TextField()
    evidencia_digital = models.JSONField(
        default=list, blank=True, help_text="URLs a audios, capturas, o geolocalización"
    )

    # Beneficios tuitivos automáticos
    inmunidad_fiscal_otorgada = models.BooleanField(default=False)
    fecha_fin_inmunidad = models.DateField(null=True, blank=True)

    estado = models.CharField(
        max_length=20,
        choices=[
            ("ingresada", "Ingresada (Medidas Cautelares Activas)"),
            ("en_mediacion", "En Mediación (MES Local)"),
            ("elevada_federal", "Elevada al Consejo Superior"),
            ("resuelta", "Resuelta"),
            ("desestimada", "Desestimada"),
        ],
        default="ingresada",
    )

    class Meta:
        verbose_name = _("Denuncia")
        verbose_name_plural = _("Denuncias")


class ScoringTallerista(TimeStampedModel):
    """
    Modelo algorítmico de gobernanza para evaluar el riesgo crediticio productivo.
    Reemplaza al Veraz/Nosis financiero por un scoring de cumplimiento físico.
    """

    tallerista = models.OneToOneField(
        "base.Contacto",
        on_delete=models.CASCADE,
        related_name="scoring_mes",
        verbose_name=_("Tallerista"),
    )
    historial_ops_finalizadas = models.PositiveIntegerField(
        default=0, verbose_name=_("OPs Finalizadas Exitosamente")
    )
    reputacion_cumplimiento = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=100.00,
        verbose_name=_("% Cumplimiento Lead Time"),
    )
    posee_sbd = models.BooleanField(
        default=False,
        verbose_name=_("Posee Sello Buen Diseño (SBD)"),
        help_text=_("Aumenta el tope de Hito Cero a 50% de forma permanente"),
    )
    fallos_arbitraje_contra = models.PositiveIntegerField(
        default=0, verbose_name=_("Fallos del Tribunal en Contra")
    )
    score_global_calculado = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00,
        verbose_name=_("Score Global de Fomento (0-100)"),
        help_text=_(
            "Si es > 90, la MES otorga Fast-Track (Adelanto Operativo Inmediato)"
        ),
    )

    class Meta:
        verbose_name = _("Scoring Productivo")
        verbose_name_plural = _("Scoring Productivo")

    def __str__(self):
        return f"Score {self.tallerista}: {self.score_global_calculado}"


# =========================================================================
# ORÁCULO DE PRECIOS, CRL Y BOLETÍN OFICIAL SECTORIAL
# =========================================================================

class TarifaConvenio(TimeStampedModel):
    """
    Oráculo de Precios y Costos de Convenio fijados por la MES.
    Establece los valores de referencia en Unidades de Cuenta Industrial (UCI).
    """

    codigo_universal = models.CharField(
        max_length=50,
        unique=True,
        verbose_name=_("Código Universal MES"),
        help_text=_("Ej: MES-SRV-CORTE, MES-SRV-APARADO, MES-SRV-MONTAJE"),
    )
    servicio_nombre = models.CharField(
        max_length=150, verbose_name=_("Denominación del Proceso / Servicio")
    )
    descripcion = models.TextField(blank=True, verbose_name=_("Alcance Técnico"))
    precio_referencia_uci = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name=_("Tarifa de Referencia (UCI)"),
        help_text=_("Valor homologado en unidades de cuenta industrial"),
    )
    vigencia_desde = models.DateField(default=timezone.now, verbose_name=_("Vigencia Desde"))
    vigencia_hasta = models.DateField(null=True, blank=True, verbose_name=_("Vigencia Hasta"))
    activo = models.BooleanField(default=True, verbose_name=_("Activo en Oráculo"))

    class Meta:
        verbose_name = _("Tarifa de Convenio (Oráculo MES)")
        verbose_name_plural = _("Tarifas de Convenio (Oráculo MES)")
        ordering = ["codigo_universal"]

    def __str__(self):
        return f"{self.codigo_universal} - {self.servicio_nombre}: {self.precio_referencia_uci} UCI"


class RevocacionCertificadoPTF(TimeStampedModel):
    """
    Lista de Revocación de Certificados (CRL) de la Autoridad Certificante MES.
    Permite invalidar credenciales de PTFs sancionados o dados de baja.
    """

    perfil_ptf = models.ForeignKey(
        PerfilPTF, on_delete=models.CASCADE, related_name="revocaciones"
    )
    hash_certificado = models.CharField(
        max_length=64, verbose_name=_("Hash SHA-256 del Certificado Revocado")
    )
    motivo_revocacion = models.TextField(verbose_name=_("Motivo / Causal de Revocación"))
    fecha_revocacion = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = _("Revocación de Certificado PTF (CRL)")
        verbose_name_plural = _("Revocaciones de Certificados PTF (CRL)")
        ordering = ["-fecha_revocacion"]

    def __str__(self):
        return f"CRL: {self.perfil_ptf.usuario.username} ({self.fecha_revocacion.strftime('%Y-%m-%d')})"


class EdicionBoletinSectorial(TimeStampedModel):
    """
    Publicación periódica oficial de la MES con resoluciones, tarifas y laudos.
    Emite fe pública fiduciaria a toda la red federada FIMCA.
    """

    comision = models.ForeignKey(
        ComisionCredito,
        on_delete=models.CASCADE,
        related_name="boletines",
        verbose_name=_("Comisión Emisora"),
    )
    numero_edicion = models.PositiveIntegerField(verbose_name=_("Número de Edición"))
    fecha_publicacion = models.DateField(default=timezone.now, verbose_name=_("Fecha de Publicación"))
    titulo = models.CharField(max_length=200, verbose_name=_("Título / Carátula"))
    sumario_resoluciones = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Sumario Normativo"),
        help_text=_("Estructura de tarifas promulgadas, laudos arbitrales y talleres homologados"),
    )
    hash_seguridad_publicacion = models.CharField(
        max_length=64,
        blank=True,
        verbose_name=_("Hash SHA-256 del Boletín"),
    )
    firma_mes = models.CharField(
        max_length=128,
        blank=True,
        verbose_name=_("Firma Ed25519 de la MES"),
    )
    publicada = models.BooleanField(default=False, verbose_name=_("Publicado Oficialmente"))

    class Meta:
        verbose_name = _("Edición Boletín Oficial Sectorial")
        verbose_name_plural = _("Ediciones Boletín Oficial Sectorial")
        unique_together = ("comision", "numero_edicion")
        ordering = ["-numero_edicion"]

    def __str__(self):
        return f"Boletín Oficial MES N° {self.numero_edicion} ({self.fecha_publicacion})"


class EvaluacionTrayectoriaSETP(TimeStampedModel):
    """
    Sistema de Evaluación de Trayectoria Productiva (SETP - Art. 2° inc. 12 y Art. 16° Ley e-OP).
    Calificación crediticia y técnica de talleres y marcas comitentes para acceso a cupos y bonificaciones FDI.
    """
    cuit_evaluado = models.CharField(max_length=20, db_index=True, verbose_name=_("CUIT Evaluado"))
    tipo_actor = models.CharField(
        max_length=20,
        choices=[("taller", _("Tallerista Façonnier")), ("comitente", _("Marca Comitente"))],
        verbose_name=_("Tipo de Actor"),
    )

    # Métricas de Taller Façonnier
    indice_cumplimiento_plazos = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("100.00"),
        verbose_name=_("Índice Cumplimiento Plazos (%)")
    )
    indice_calidad_tecnica = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("100.00"),
        verbose_name=_("Índice Calidad Técnica (%)")
    )
    ops_cumplidas_exitosas = models.PositiveIntegerField(
        default=0, verbose_name=_("e-OPs Cumplidas Exitosamente")
    )

    # Métricas de Marca Comitente
    indice_puntualidad_jit = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("100.00"),
        verbose_name=_("Índice Puntualidad Abastecimiento JIT (%)")
    )
    indice_pago_vencimientos = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("100.00"),
        verbose_name=_("Índice Pago en Término (%)")
    )
    dias_mora_historicos_acumulados = models.PositiveIntegerField(
        default=0, verbose_name=_("Días de Mora Acumulados")
    )

    # Scoring y Régimen de Arranque en Frío
    score_setp = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("70.00"),
        verbose_name=_("Score SETP (0 a 100)")
    )
    categoria_setp = models.CharField(
        max_length=5,
        choices=[("A+", "A+"), ("A", "A"), ("B", "B"), ("C", "C")],
        default="B",
        verbose_name=_("Categoría SETP"),
    )
    es_arranque_en_frio = models.BooleanField(
        default=True,
        verbose_name=_("Régimen Arranque en Frío"),
        help_text=_("Otorga cupo inicial a unidades productivas nuevas sin historial fabril previo.")
    )
    cupo_operativo_uci = models.DecimalField(
        max_digits=15, decimal_places=2, default=Decimal("5000.00"),
        verbose_name=_("Cupo Operativo Máximo (UCI)")
    )

    class Meta:
        verbose_name = _("Evaluación Trayectoria SETP")
        verbose_name_plural = _("Evaluaciones de Trayectoria SETP")
        ordering = ["-score_setp"]

    def __str__(self):
        return f"SETP {self.cuit_evaluado} [{self.get_tipo_actor_display()}]: {self.score_setp} pts ({self.categoria_setp})"

    def recalcular_categoria(self):
        """Asigna categoría según umbrales reglamentarios."""
        if self.score_setp >= Decimal("90.00"):
            self.categoria_setp = "A+"
        elif self.score_setp >= Decimal("80.00"):
            self.categoria_setp = "A"
        elif self.score_setp >= Decimal("65.00"):
            self.categoria_setp = "B"
        else:
            self.categoria_setp = "C"


class CertificadoDiligenciaDebida(TimeStampedModel):
    """
    Certificado de Diligencia Debida Laboral (CDD / CDD-P - Art. 22° Ley e-OP).
    Confiere presunción legal iuris tantum de cumplimiento del deber de control del Art. 30 LCT
    (Puerto Seguro Laboral para las marcas comitentes frente a reclamos laborales).
    """
    tallerista = models.ForeignKey(
        "base.Contacto", on_delete=models.CASCADE, related_name="certificados_cdd",
        verbose_name=_("Taller Façonnier"),
    )
    comitente = models.ForeignKey(
        "base.Contacto", on_delete=models.CASCADE, related_name="certificados_cdd_comitente",
        verbose_name=_("Marca Comitente"),
    )
    eop_asociada = models.ForeignKey(
        "base.ContratoEOP", on_delete=models.CASCADE, related_name="certificados_cdd",
        verbose_name=_("e-OP Colateralizada"),
    )

    TIPO_CHOICES = [
        ("cdd_provisorio", _("CDD Provisorio (CDD-P - Meses 1 a 12, Rampa de Formalización)")),
        ("cdd_definitivo", _("CDD Definitivo (Mes 13 en adelante)")),
    ]
    tipo = models.CharField(
        max_length=20, choices=TIPO_CHOICES, default="cdd_provisorio", verbose_name=_("Tipo de Certificado")
    )

    periodo_mes_anio = models.CharField(max_length=7, verbose_name=_("Período Fiscal (YYYY-MM)"))
    f931_presentado = models.BooleanField(default=False, verbose_name=_("F.931 Presentado y Cancelado"))
    dotacion_declarada = models.PositiveIntegerField(default=0, verbose_name=_("Dotación de Trabajadores Declarada"))
    poliza_art_vigente = models.BooleanField(default=False, verbose_name=_("Póliza de ART Vigente"))
    bancarizacion_salarios_verificada = models.BooleanField(
        default=False, verbose_name=_("Bancarización de Haberes (SIPA) Verificada")
    )
    situacion_fiscal_arca_regular = models.BooleanField(
        default=False, verbose_name=_("Situación Fiscal ARCA Regular")
    )

    estado_puerto_seguro = models.CharField(
        max_length=20,
        choices=[
            ("vigente", _("Vigente (Puerto Seguro Activo)")),
            ("suspendido", _("Suspendido")),
            ("revocado", _("Revocado")),
        ],
        default="vigente",
        verbose_name=_("Estado Puerto Seguro Laboral"),
    )
    hash_verificacion_cdd = models.CharField(
        max_length=64, blank=True, verbose_name=_("Hash SHA-256 de Constatación")
    )

    class Meta:
        verbose_name = _("Certificado Diligencia Debida (CDD)")
        verbose_name_plural = _("Certificados Diligencia Debida (CDD)")
        ordering = ["-creado_en"]

    def __str__(self):
        return f"CDD {self.tipo} - Taller: {self.tallerista} | Periodo: {self.periodo_mes_anio} [{self.estado_puerto_seguro}]"


class PeritajeCalidadINTI(TimeStampedModel):
    """
    Procedimiento Sumarísimo de Objeción Técnica y Peritaje INTI (Arts. 11.2 y 13° Ley e-OP).
    Se activa si la comitente objeta mermas o defectos dentro de los 5 días hábiles de la entrega.
    Suspende exclusivamente la liberación del tramo RCF.
    """
    eop = models.ForeignKey(
        "base.ContratoEOP", on_delete=models.CASCADE, related_name="peritajes_inti",
        verbose_name=_("e-OP Auditada"),
    )
    comitente = models.ForeignKey(
        "base.Contacto", on_delete=models.CASCADE, related_name="objeciones_calidad_comitente"
    )
    tallerista = models.ForeignKey(
        "base.Contacto", on_delete=models.CASCADE, related_name="objeciones_calidad_taller"
    )
    descripcion_objecion = models.TextField(verbose_name=_("Fundamento de la Objeción Técnica"))
    fecha_objecion = models.DateTimeField(default=timezone.now, verbose_name=_("Fecha de Notificación"))
    fecha_limite_dictamen = models.DateTimeField(verbose_name=_("Plazo Perentorio Dictamen INTI (5 días)"))

    dictamen_tecnico_inti = models.TextField(blank=True, null=True, verbose_name=_("Dictamen Pericial INTI"))
    defecto_imputable_taller = models.BooleanField(
        null=True, blank=True, verbose_name=_("¿Defecto Técnico Imputable al Taller?")
    )
    arancel_peritaje_ars = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"),
        verbose_name=_("Arancel Pericial (2 SMVM)"),
    )
    estado = models.CharField(
        max_length=20,
        choices=[
            ("iniciado", _("Objeción Notificada")),
            ("en_peritaje", _("En Peritaje de Laboratorio INTI")),
            ("laudado_conforme", _("Laudado: Rechazo de Objeción (Libera RCF)")),
            ("laudado_con_merma", _("Laudado: Falla Técnica Confirmada")),
        ],
        default="iniciado",
    )

    class Meta:
        verbose_name = _("Peritaje de Calidad INTI")
        verbose_name_plural = _("Peritajes de Calidad INTI")
        ordering = ["-fecha_objecion"]

    def __str__(self):
        return f"Peritaje INTI e-OP {self.eop.numero or self.eop.id} [{self.get_estado_display()}]"


class LibretaTrabajoDomicilio(TimeStampedModel):
    """
    Sub-régimen de Libreta Digital de Trabajo a Domicilio (Ley N° 12.713 y Art. 28° Ley e-OP).
    Aplica para costureros/as y artesanos a domicilio integrados al FDI sin estructura de taller fabril.
    """
    costurero = models.ForeignKey(
        "base.Contacto", on_delete=models.CASCADE, related_name="libretas_domicilio"
    )
    marca_comitente = models.ForeignKey(
        "base.Contacto", on_delete=models.CASCADE, related_name="libretas_domicilio_marca"
    )
    eop_asociada = models.ForeignKey(
        "base.ContratoEOP", on_delete=models.CASCADE, related_name="libretas_domicilio"
    )
    tarifa_paritaria_garantizada_ars = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name=_("Tarifa de Convenio Garantizada")
    )
    prendas_recibidas = models.PositiveIntegerField(default=0)
    prendas_entregadas = models.PositiveIntegerField(default=0)
    retencion_previsional_fdi_ars = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"),
        verbose_name=_("Cargas Sociales e Integración Previsional FDI (100%)"),
    )
    responsabilidad_solidaria_directa = models.BooleanField(
        default=True,
        verbose_name=_("Responsabilidad Solidaria Directa Irrenunciable (Art. 4° Ley 12.713)"),
    )

    class Meta:
        verbose_name = _("Libreta Digital Trabajo a Domicilio")
        verbose_name_plural = _("Libretas Digitales Trabajo a Domicilio")

    def __str__(self):
        return f"Libreta 12.713: {self.costurero} - e-OP {self.eop_asociada.numero or self.eop_asociada.id}"


# =====================================================================
# INFRAESTRUCTURA FIDUCIARIA Y MERCADO DE CAPITALES (FDI)
# Marco Legal: Anteproyecto de Ley e-OP Arts. 14°, 16°, 17°, 20° bis y Anexos
# =====================================================================

class CarteraTitulizableBIP(TimeStampedModel):
    """
    Cartera homogénea de contratos e-OP colateralizables y auditados por el FDI,
    aptos para titulización y emisión de Bonos de Inversión Productiva (BIP) conforme al Art. 17°.
    """
    codigo_cartera = models.CharField(
        max_length=60, unique=True, verbose_name=_("Código de Cartera Titulizable")
    )
    descripcion = models.CharField(max_length=200, blank=True, verbose_name=_("Descripción de la Cartera"))
    contratos = models.ManyToManyField(
        "base.ContratoEOP", related_name="carteras_bip", verbose_name=_("Contratos e-OP Asignados")
    )
    monto_nominal_total_ars = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00"), verbose_name=_("Monto Nominal Total (ARS)")
    )
    monto_nominal_total_uci = models.DecimalField(
        max_digits=18, decimal_places=4, default=Decimal("0.00"), verbose_name=_("Monto Nominal Total (UCI)")
    )
    calificacion_promedio_setp = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("70.00"), verbose_name=_("Score SETP Promedio Ponderado")
    )
    estado = models.CharField(
        max_length=25,
        choices=[
            ("en_conformacion", _("En Conformación")),
            ("auditada_comite", _("Auditada y Aprobada por Comité")),
            ("titulizada", _("Titulizada (Títulos Emitidos)")),
            ("liquidada", _("Liquidada y Cancelada")),
        ],
        default="en_conformacion",
        verbose_name=_("Estado de la Cartera")
    )
    fecha_corte = models.DateField(null=True, blank=True, verbose_name=_("Fecha de Corte de la Cartera"))

    class Meta:
        verbose_name = _("Cartera Titulizable BIP")
        verbose_name_plural = _("Carteras Titulizables BIP")
        ordering = ["-creado_en"]

    def __str__(self):
        return f"{self.codigo_cartera} [{self.get_estado_display()}] — $ {self.monto_nominal_total_ars}"

    def recalcular_totales(self):
        """Recalcula el valor nominal agregado y el scoring promedio ponderado de las e-OPs asignadas."""
        contratos_qs = self.contratos.all()
        total_uci = sum((c.monto_total_uci for c in contratos_qs), Decimal("0.00"))
        self.monto_nominal_total_uci = total_uci
        self.save(update_fields=["monto_nominal_total_uci"])


class SerieBonoBIP(TimeStampedModel):
    """
    Título de Deuda / Bono de Inversión Productiva (BIP) de Corto Plazo (60 a 180 días).
    Emisión fiduciaria en el Mercado de Capitales bajo normativa CNV (RG 917/2021)
    con etiqueta de Bono Social, Verde o Sustentable (SVS).
    """
    MONEDA_CHOICES = [
        ("uci", _("Unidad de Cuenta Industrial (UCI)")),
        ("uva", _("Unidad de Valor Adquisitivo (UVA)")),
        ("ars", _("Pesos Argentinos (ARS)")),
        ("usd", _("Dólares Estadounidenses (USD)")),
    ]

    TRAMO_CHOICES = [
        ("institucional", _("Tramo Institucional (FCI / Bancos / Aseguradoras)")),
        ("minorista_alyc", _("Tramo Minorista / Inversores Pyme (ALyC)")),
    ]

    cartera_subyacente = models.ForeignKey(
        CarteraTitulizableBIP, on_delete=models.PROTECT, related_name="series_bonos",
        verbose_name=_("Cartera Subyacente Titulizada")
    )
    codigo_ticker = models.CharField(
        max_length=20, unique=True, verbose_name=_("Ticker Bursátil (BYMA/MAE)"),
        help_text=_("Ej: BIP-2026-I, BIP-UCI-001")
    )
    numero_serie = models.PositiveIntegerField(default=1, verbose_name=_("Número de Serie"))
    plazo_dias = models.PositiveIntegerField(
        default=90, choices=[(60, "60 días"), (90, "90 días"), (120, "120 días"), (180, "180 días")],
        verbose_name=_("Plazo del Bono (Días Corridos)")
    )
    moneda = models.CharField(max_length=10, choices=MONEDA_CHOICES, default="uci", verbose_name=_("Moneda de Emisión"))
    monto_emision_nominal = models.DecimalField(
        max_digits=18, decimal_places=2, verbose_name=_("Monto Nominal Emitido")
    )
    tasa_interes_anual = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.00"), verbose_name=_("Tasa de Interés Nominal Anual (TNA %)")
    )
    fecha_emision = models.DateField(default=timezone.now, verbose_name=_("Fecha de Emisión"))
    fecha_vencimiento = models.DateField(verbose_name=_("Fecha de Vencimiento y Amortización"))

    # Cumplimiento Regulatorio CNV RG 917/2021 (Bonos SVS)
    es_etiqueta_svs = models.BooleanField(
        default=True, verbose_name=_("Etiqueta SVS (Bono Social y Sustentable)"),
        help_text=_("Acredita impacto laboral formal y desarrollo productivo federal.")
    )
    revisor_externo_cnv = models.CharField(
        max_length=150, blank=True, verbose_name=_("Revisor Externo Independiente (Registro CNV)")
    )
    hash_seguridad_prospecto = models.CharField(
        max_length=64, blank=True, verbose_name=_("Hash SHA-256 del Prospecto Homologado")
    )

    estado = models.CharField(
        max_length=25,
        choices=[
            ("solicitud_cnv", _("En Homologación CNV")),
            ("en_colocacion", _("En Período de Colocación Bursátil")),
            ("vigente", _("Vigente / En Circulación")),
            ("amortizado", _("Totalmente Amortizado")),
            ("incumplido", _("En Ejecución de Garantías")),
        ],
        default="solicitud_cnv",
        verbose_name=_("Estado de la Serie")
    )

    class Meta:
        verbose_name = _("Serie de Bonos BIP")
        verbose_name_plural = _("Series de Bonos BIP (Mercado de Capitales)")
        ordering = ["-fecha_emision", "numero_serie"]

    def __str__(self):
        return f"{self.codigo_ticker} ({self.get_moneda_display()}) - Vto: {self.fecha_vencimiento} [{self.get_estado_display()}]"


class SubcuentaReservaFondo(TimeStampedModel):
    """
    Subcuentas fiduciarias de liquidez y amortiguadores de riesgo del FDI
    instituidas por el Art. 16° de la Ley e-OP para aislar insolvencias y contingencias.
    """
    TIPO_RESERVA_CHOICES = [
        ("garantia_comitente", _("Reserva de Garantía Comitente (5% Retención s/e-OP)")),
        ("mora_operativa", _("Reserva por Mora Operativa del Taller (0,8% Canon FDI)")),
        ("fondo_laboral_fael", _("Fondo Laboral FAEL y Caución LCT (0,5% Canon FDI)")),
        ("liquidez_contingente", _("Facilidad de Liquidez Contingente (Hasta 5% Programa)")),
    ]

    tipo_reserva = models.CharField(
        max_length=30, choices=TIPO_RESERVA_CHOICES, unique=True, verbose_name=_("Tipo de Subcuenta Fiduciaria")
    )
    descripcion = models.TextField(blank=True, verbose_name=_("Finalidad y Destino Específico"))
    saldo_disponible_ars = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00"), verbose_name=_("Saldo Disponible (ARS)")
    )
    saldo_bloqueado_ars = models.DecimalField(
        max_digits=18, decimal_places=2, default=Decimal("0.00"), verbose_name=_("Saldo Comprometido/Bloqueado (ARS)")
    )
    alicuota_canon_pct = models.DecimalField(
        max_digits=4, decimal_places=2, default=Decimal("0.00"), verbose_name=_("Alícuota s/Canon Fiduciario (%)")
    )

    class Meta:
        verbose_name = _("Subcuenta de Reserva Fiduciaria")
        verbose_name_plural = _("Subcuentas de Reserva Fiduciaria (Art. 16°)")

    def __str__(self):
        return f"[{self.get_tipo_reserva_display()}] Saldo: $ {self.saldo_disponible_ars}"


class PolizaColectivaStock(TimeStampedModel):
    """
    Póliza Colectiva de Seguro de Stock en Custodia (Art. 20° bis Ley e-OP).
    Contratada centralizadamente por el FDI ante entidades aseguradoras autorizadas por la SSN.
    Cubre el valor $c_{\text{BOM}}$ entregado a los talleres contra siniestros, incendio y robo.
    """
    numero_poliza = models.CharField(max_length=60, unique=True, verbose_name=_("Número de Póliza Oficial SSN"))
    compania_aseguradora = models.CharField(max_length=150, verbose_name=_("Compañía Aseguradora (SSN)"))
    fecha_vigencia_desde = models.DateField(verbose_name=_("Inicio de Vigencia"))
    fecha_vigencia_hasta = models.DateField(verbose_name=_("Fin de Vigencia"))
    monto_maximo_cobertura_ars = models.DecimalField(
        max_digits=18, decimal_places=2, verbose_name=_("Límite Global de Cobertura (ARS)")
    )
    tasa_prima_anual_pct = models.DecimalField(
        max_digits=4, decimal_places=2, default=Decimal("0.50"),
        verbose_name=_("Tasa de Prima s/Valor BOM (%)"),
        help_text=_("Tope legal: 0,5% s/BOM financiado vía canon fiduciario de stock.")
    )
    activa = models.BooleanField(default=True, verbose_name=_("Póliza Activa"))

    class Meta:
        verbose_name = _("Póliza Colectiva de Stock en Custodia")
        verbose_name_plural = _("Pólizas Colectivas de Stock (Art. 20° bis)")

    def __str__(self):
        return f"Póliza {self.numero_poliza} ({self.compania_aseguradora}) - Cobertura: $ {self.monto_maximo_cobertura_ars}"


class CuentaEspecialCompensacion(TimeStampedModel):
    """
    Cuentas Especiales de Compensación y Liquidación Manufacturera (Art. 14° y Anexo I).
    Cuentas abiertas en entidades financieras bancarias o de pago bajo régimen especial BCRA.
    Gozan de exención automática del Impuesto al Cheque (Ley 25.413) e inembargabilidad operativa.
    """
    contacto = models.ForeignKey(
        "base.Contacto", on_delete=models.CASCADE, related_name="cuentas_especiales_compensacion",
        verbose_name=_("Titular (Marca o Taller)")
    )
    cbu_cvu = models.CharField(max_length=22, unique=True, verbose_name=_("CBU / CVU Especial BCRA"))
    alias = models.CharField(max_length=50, blank=True, verbose_name=_("Alias Bancario"))
    entidad_bancaria = models.CharField(max_length=100, verbose_name=_("Banco / Proveedor de Servicios de Pago"))
    numero_cuenta = models.CharField(max_length=50, blank=True, verbose_name=_("Número de Cuenta"))
    
    exencion_impuesto_cheque = models.BooleanField(
        default=True, verbose_name=_("Exención Impuesto Débitos y Créditos (Ley 25.413)"),
        help_text=_("Exención aplicable exclusivamente a liquidaciones de e-OPs acreditadas por el FDI.")
    )
    inembargabilidad_activa = models.BooleanField(
        default=True, verbose_name=_("Inembargabilidad Operativa Preexistente"),
        help_text=_("Los fondos no son pasibles de embargo por deudas bancarias anteriores del titular.")
    )
    activa = models.BooleanField(default=True, verbose_name=_("Cuenta Habilitada"))

    class Meta:
        verbose_name = _("Cuenta Especial de Compensación BCRA")
        verbose_name_plural = _("Cuentas Especiales de Compensación (Art. 14°)")
        ordering = ["contacto", "-creado_en"]

    def __str__(self):
        return f"{self.contacto.nombre} - {self.entidad_bancaria} ({self.cbu_cvu})"


