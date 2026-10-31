import uuid
from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes.fields import GenericForeignKey
from simple_history.models import HistoricalRecords


class TimeStampedModel(models.Model):
    """
    Clase abstracta que provee campos de auditoría temporal
    creado_en y modificado_en automáticamente a cualquier modelo de FIMCA Core.
    """
    creado_en = models.DateTimeField(auto_now_add=True, verbose_name="Creado")
    modificado_en = models.DateTimeField(auto_now=True, verbose_name="Modificado")
    history = HistoricalRecords(inherit=True)

    class Meta:
        abstract = True


class ConfiguracionNodo(TimeStampedModel):
    """
    Configuración institucional y criptográfica del Nodo FIMCA Core.
    """
    nombre_nodo = models.CharField(max_length=150, verbose_name="Nombre del Nodo")
    cuit = models.CharField(max_length=20, verbose_name="CUIT / Identificador Fiscal")
    nodo_id = models.CharField(max_length=100, unique=True, verbose_name="ID de Red del Nodo")
    rol = models.CharField(max_length=50, default="MES", verbose_name="Rol en la Red")
    clave_publica_ed25519 = models.CharField(max_length=64, blank=True, verbose_name="Clave Pública Ed25519")
    nodo_mes_endpoint = models.URLField(max_length=255, blank=True, default="", verbose_name="Endpoint MES")

    class Meta:
        verbose_name = "Configuración del Nodo"
        verbose_name_plural = "Configuraciones del Nodo"

    def __str__(self):
        return f"{self.nombre_nodo} ({self.cuit})"



class Moneda(TimeStampedModel):
    """
    Monedas soportadas en el sistema de compensación y liquidación (Clearing).
    """
    nombre = models.CharField(max_length=50, verbose_name="Nombre de la moneda")
    codigo = models.CharField(max_length=3, unique=True, verbose_name="Código (ISO 4217)")
    simbolo = models.CharField(max_length=10, verbose_name="Símbolo")
    activa = models.BooleanField(default=True, verbose_name="Activa")

    class Meta:
        verbose_name = "Moneda"
        verbose_name_plural = "Monedas"

    def __str__(self):
        return f"{self.codigo} ({self.simbolo})"


class Secuencia(TimeStampedModel):
    """
    Secuencias alfanuméricas para dictámenes, resoluciones y comunicaciones oficiales.
    """
    nombre = models.CharField(max_length=100, verbose_name="Nombre")
    codigo = models.CharField(max_length=50, unique=True, verbose_name="Código identificador")
    prefijo = models.CharField(max_length=20, blank=True, default="", verbose_name="Prefijo")
    sufijo = models.CharField(max_length=20, blank=True, default="", verbose_name="Sufijo")
    siguiente_numero = models.PositiveIntegerField(default=1, verbose_name="Siguiente número")
    incremento = models.PositiveIntegerField(default=1, verbose_name="Incremento")
    longitud_relleno = models.PositiveIntegerField(default=6, verbose_name="Longitud de relleno con ceros")
    activo = models.BooleanField(default=True, verbose_name="Activo")

    class Meta:
        verbose_name = "Secuencia"
        verbose_name_plural = "Secuencias"

    def __str__(self):
        return f"{self.nombre} ({self.codigo})"


class DocumentoAdjunto(TimeStampedModel):
    """
    Archivo adjunto genérico para actos de la Mesa de Enlace o Notificaciones Oficiales.
    """
    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    nombre = models.CharField(max_length=255, verbose_name="Nombre del archivo")
    archivo = models.FileField(upload_to="adjuntos/fimca/", verbose_name="Archivo")
    mimetype = models.CharField(max_length=100, blank=True, verbose_name="Tipo MIME")
    tamano = models.PositiveIntegerField(default=0, verbose_name="Tamaño (bytes)")
    descripcion = models.TextField(blank=True, verbose_name="Descripción")

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="+",
    )
    object_id = models.PositiveIntegerField()
    contenido_objeto = GenericForeignKey("content_type", "object_id")

    class Meta:
        ordering = ["-creado_en"]
        verbose_name = "Documento adjunto"
        verbose_name_plural = "Documentos adjuntos"

    def __str__(self):
        return f"{self.nombre} ({self.mimetype})"


class Contacto(TimeStampedModel):
    """
    Entidad participante de la Red FIMCA (Taller, Marca Comitente, Banco, Sindicato, PTF).
    Actúa como contraparte identificable en el clearing y las resoluciones de la MES.
    """
    TIPO_CHOICES = [
        ("taller", "Taller Façonnier"),
        ("marca", "Marca Comitente"),
        ("banco", "Entidad Financiera"),
        ("ptf", "Perito Técnico de Fasón"),
        ("sindicato", "Asociación Gremial"),
        ("camara", "Cámara Empresaria"),
    ]
    nombre = models.CharField(max_length=200, verbose_name="Razón Social / Nombre")
    codigo = models.CharField(max_length=50, unique=True, verbose_name="Código de Identificación")
    cuit = models.CharField(max_length=20, unique=True, verbose_name="CUIT")
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES, default="taller", verbose_name="Tipo de Entidad")
    email = models.EmailField(blank=True, verbose_name="Email de Contacto")
    activo = models.BooleanField(default=True, verbose_name="Activo")

    class Meta:
        verbose_name = "Contacto"
        verbose_name_plural = "Contactos"
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.cuit})"

