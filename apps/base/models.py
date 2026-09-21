import datetime
import hashlib
import uuid
import uuid6
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.contrib.contenttypes.fields import GenericRelation
from simple_history.models import HistoricalRecords
from apps.base.services import SecuenciaService


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


from django.contrib.auth import get_user_model

User = get_user_model()


class PerfilCriptografico(TimeStampedModel):
    """
    Identidad digital local para los usuarios del ERP (Empleados de la Marca, Taller o PTF).
    Permite estampar firmas criptográficas en nombre de la empresa dueña del nodo.
    """

    usuario = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="perfil_crypto"
    )
    clave_publica_ed25519 = models.CharField(
        max_length=64,
        verbose_name="Clave Pública Local (Ed25519)",
        help_text="Clave pública del operador del ERP local para firmar e-OPs o Hitos.",
    )

    class Meta:
        verbose_name = "Perfil Criptográfico Local"
        verbose_name_plural = "Perfiles Criptográficos Locales"

    def __str__(self):
        return f"Crypto Profile: {self.usuario.username}"


class DocumentoFirmableMixin(models.Model):
    """
    Mixin para dotar a cualquier documento de capacidades criptográficas
    (generación de payload canónico, hashing y almacenamiento de firmas).
    Al usar JSONField para firmas, django-simple-history tomará snapshots exactos.
    """

    # Identificador único global inmutable
    uuid_identificador = models.UUIDField(
        default=uuid6.uuid7,
        editable=False,
        unique=True,
        verbose_name="Identificador Único Criptográfico",
    )
    # Hash SHA-256 del payload canónico
    hash_seguridad = models.CharField(
        max_length=64,
        blank=True,
        editable=False,
        verbose_name="Hash Criptográfico (SHA-256)",
        help_text="Digest inmutable generado al confirmar/sellar el documento.",
    )
    # Firmas JSON { "rol": { "firmante_id": X, "firma_hex": "...", "timestamp": "..." } }
    firmas_digitales = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Firmas Digitales (Ed25519)",
        help_text="Esquema Multifirma. Modificar este campo generará un registro histórico.",
    )

    class Meta:
        abstract = True

    def generar_payload_canonico(self):
        """
        Debe ser implementado por el modelo hijo para retornar
        el string JSON determinista que será hasheado y firmado.
        """
        raise NotImplementedError(
            "El modelo debe implementar generar_payload_canonico()"
        )

    def calcular_hash_documento(self):
        """Calcula el hash SHA-256 canónico del documento."""
        payload_str = self.generar_payload_canonico()
        return hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

    def sellar_hash_seguridad(self):
        """
        Fija el hash criptográfico si aún no fue emitido.
        Se ejecuta al confirmar la orden para hacerla inmutable.
        """
        if not self.hash_seguridad:
            self.hash_seguridad = self.calcular_hash_documento()
            self.save(update_fields=["hash_seguridad"])
        return self.hash_seguridad

    def verificar_integridad_hash(self):
        """Verifica si los datos canónicos coinciden con el hash sellado."""
        if not self.hash_seguridad:
            return False
        return self.calcular_hash_documento() == self.hash_seguridad

    def agregar_firma(self, rol, actor_id, firma_hex):
        """
        Agrega una firma al JSONField. Al llamar a save(), simple-history
        tomará un snapshot con el documento exacto y las firmas presentes.
        """
        firmas = dict(self.firmas_digitales)
        firmas[rol] = {
            "actor_id": actor_id,
            "firma_hex": firma_hex,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        self.firmas_digitales = firmas
        self.save(update_fields=["firmas_digitales"])


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

    SECUENCIA_CODIGO = None

    class Meta:
        abstract = True
        ordering = ["-fecha", "-numero"]

    def save(self, *args, **kwargs):
        if not self.numero and self.SECUENCIA_CODIGO:
            self.numero = SecuenciaService.obtener_siguiente_numero(self.SECUENCIA_CODIGO, fecha=self.fecha)
        super().save(*args, **kwargs)

class Secuencia(TimeStampedModel):
    """
    Motor centralizado de secuencias alfanuméricas consecutivas para documentos.
    Compatible con normativas AFIP/ARCA y documentos internos.
    """
    codigo = models.CharField(max_length=50, unique=True, verbose_name="Código de la secuencia")
    nombre = models.CharField(max_length=100, verbose_name="Nombre")
    prefijo = models.CharField(max_length=20, blank=True, default="", verbose_name="Prefijo")
    sufijo = models.CharField(max_length=20, blank=True, default="", verbose_name="Sufijo")
    longitud_relleno = models.PositiveIntegerField(default=8, verbose_name="Longitud de relleno (Padding)")
    siguiente_numero = models.PositiveIntegerField(default=1, verbose_name="Siguiente número")
    incremento = models.PositiveIntegerField(default=1, verbose_name="Incremento")
    punto_venta = models.PositiveIntegerField(blank=True, null=True, verbose_name="Punto de Venta (AFIP)")
    
    reinicio_anual = models.BooleanField(default=False, verbose_name="Reiniciar cada año")
    reinicio_mensual = models.BooleanField(default=False, verbose_name="Reiniciar cada mes")
    ultimo_reinicio = models.DateField(blank=True, null=True, verbose_name="Último reinicio")
    activo = models.BooleanField(default=True, verbose_name="Activo")

    class Meta:
        verbose_name = "Secuencia de documento"
        verbose_name_plural = "Secuencias de documentos"

    def __str__(self):
        return f"{self.nombre} ({self.codigo})"


class Moneda(TimeStampedModel):
    """
    Modelo para gestión de monedas de cuenta y tipo de cambio.
    """

    nombre = models.CharField(max_length=50, verbose_name="Nombre de la moneda")
    codigo = models.CharField(
        max_length=3, unique=True, verbose_name="Código (ISO 4217)"
    )
    simbolo = models.CharField(max_length=10, verbose_name="Símbolo")
    afip_codigo = models.CharField(
        max_length=3,
        default="PES",
        verbose_name="Código AFIP (WSFE)",
        help_text="Ej. PES, DOL, EUR",
    )
    activa = models.BooleanField(default=True, verbose_name="Activa")

    class Meta:
        verbose_name = "Moneda"
        verbose_name_plural = "Monedas"
        ordering = ["codigo"]

    def __str__(self):
        return f"{self.codigo} - {self.nombre} ({self.simbolo})"


class ConfiguracionEmpresa(TimeStampedModel):
    """
    Singleton que almacena la configuración de la empresa dueña del ERP (Single-Tenant).
    Centraliza datos fiscales, credenciales AFIP y parámetros globales del sistema.
    """

    ENTORNO_AFIP_CHOICES = [
        ("homologacion", "Homologación (Testing)"),
        ("produccion", "Producción (Real)"),
    ]

    CONDICION_IVA_CHOICES = [
        ("responsable_inscripto", "Responsable Inscripto"),
        ("monotributista", "Monotributista"),
        ("exento", "Exento"),
    ]

    # Datos Comerciales
    razon_social = models.CharField(max_length=200, verbose_name="Razón Social")
    nombre_fantasia = models.CharField(
        max_length=200, blank=True, verbose_name="Nombre de Fantasía"
    )
    cuit = models.CharField(max_length=20, verbose_name="CUIT (Empresa)")
    condicion_iva = models.CharField(
        max_length=30,
        choices=CONDICION_IVA_CHOICES,
        default="responsable_inscripto",
        verbose_name="Condición frente al IVA",
    )
    ingresos_brutos = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Número de Ingresos Brutos",
        help_text="Número de inscripción en IIBB o Convenio Multilateral",
    )
    fecha_inicio_actividades = models.DateField(
        null=True,
        blank=True,
        verbose_name="Fecha de Inicio de Actividades",
    )

    # Regímenes Especiales / Agentes Fiscales
    es_agente_percepcion_iva = models.BooleanField(
        default=False,
        verbose_name="Es Agente de Percepción de IVA",
        help_text="Habilita la liquidación de Percepciones de IVA en ventas a clientes.",
    )
    es_agente_percepcion_iibb = models.BooleanField(
        default=False,
        verbose_name="Es Agente de Percepción de IIBB",
        help_text="Habilita la liquidación de Percepciones de Ingresos Brutos (ARBA, AGIP, etc.).",
    )
    es_agente_retencion_iva = models.BooleanField(
        default=False,
        verbose_name="Es Agente de Retención de IVA",
        help_text="Exige retener IVA a proveedores según RG 2854 al efectuar pagos.",
    )
    es_agente_retencion_ganancias = models.BooleanField(
        default=False,
        verbose_name="Es Agente de Retención de Ganancias",
        help_text="Exige retener Impuesto a las Ganancias según RG 830 al efectuar pagos.",
    )
    direccion = models.CharField(
        max_length=250, blank=True, verbose_name="Dirección Comercial"
    )
    telefono = models.CharField(max_length=50, blank=True, verbose_name="Teléfono")
    email = models.EmailField(blank=True, verbose_name="Correo Electrónico")
    logo = models.ImageField(
        upload_to="empresa/", blank=True, null=True, verbose_name="Logo Institucional"
    )

    # Facturación y AFIP
    afip_entorno = models.CharField(
        max_length=20,
        choices=ENTORNO_AFIP_CHOICES,
        default="homologacion",
        verbose_name="Entorno AFIP",
    )
    afip_certificado = models.FileField(
        upload_to="afip/certs/",
        blank=True,
        null=True,
        verbose_name="Certificado CRT (X.509)",
        help_text="Archivo .crt o .pem de AFIP",
    )
    afip_clave_privada = models.FileField(
        upload_to="afip/keys/",
        blank=True,
        null=True,
        verbose_name="Clave Privada",
        help_text="Archivo .key",
    )

    # Federación MES (FIMCA)
    nodo_mes_identificador = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Identificador Nodo MES",
        help_text="Ej: nodo-sur-lomas",
    )
    nodo_mes_endpoint = models.URLField(
        blank=True,
        verbose_name="Endpoint Subdominio MES",
        help_text="Ej: https://api.sur.mes.indinopy.ar",
    )

    # Laboral / Nómina
    art_nombre = models.CharField(
        max_length=100, blank=True, null=True,
        verbose_name="Nombre de la ART",
        help_text="Aseguradora de Riesgos de Trabajo (Ej: Provincia ART, Galeno)"
    )
    art_porcentaje = models.DecimalField(
        max_digits=5, decimal_places=2, default=0.00,
        verbose_name="Alícuota ART (%)",
        help_text="Porcentaje variable aplicado sobre la masa salarial remunerativa."
    )
    art_fijo_por_empleado = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00,
        verbose_name="Cuota fija ART ($)",
        help_text="Monto fijo mensual a abonar por cada empleado (Fondo Fiduciario de Enfermedades Profesionales)."
    )

    class Meta:
        verbose_name = "Configuración de Empresa"
        verbose_name_plural = "Configuración de Empresa"

    def __str__(self):
        return f"{self.razon_social} ({self.cuit})"

    def save(self, *args, **kwargs):
        """Asegura que solo exista un registro de configuración (Singleton)."""
        if self.__class__.objects.count() > 0 and not self.pk:
            raise ValidationError(
                "No se puede crear más de una configuración de empresa en modo Single-Tenant."
            )
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        """Devuelve la configuración actual o crea una por defecto."""
        obj, created = cls.objects.get_or_create(
            defaults={
                "razon_social": "Indinopy S.A.",
                "cuit": "30000000000",
            }
        )
        return obj
