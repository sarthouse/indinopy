import datetime
import hashlib
import uuid
from django.core.exceptions import ValidationError
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
        default=uuid.uuid4,
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

    class Meta:
        abstract = True
        ordering = ["-fecha", "-numero"]


class Moneda(TimeStampedModel):
    """
    Modelo para monedas (Odoo: res.currency).
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
    Equivalente a res.company en Odoo.
    """

    ENTORNO_AFIP_CHOICES = [
        ("homologacion", "Homologación (Testing)"),
        ("produccion", "Producción (Real)"),
    ]

    # Datos Comerciales
    razon_social = models.CharField(max_length=200, verbose_name="Razón Social")
    nombre_fantasia = models.CharField(
        max_length=200, blank=True, verbose_name="Nombre de Fantasía"
    )
    cuit = models.CharField(max_length=20, verbose_name="CUIT (Empresa)")
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

    # Federación MES (RIGI Conurbano)
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
