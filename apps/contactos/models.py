from decimal import Decimal
from django.contrib.gis.db import models
from django.utils.translation import gettext_lazy as _

from apps.base.models import TimeStampedModel


class CategoriaContacto(TimeStampedModel):
    """
    Clasificación estructural y jerárquica de contactos.
    Ejemplos: 'Distribuidores', 'Proveedores', 'Clientes'
    """

    nombre = models.CharField(max_length=100, unique=True, verbose_name=_("Nombre"))
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="subcategorias",
        verbose_name=_("Categoría padre"),
    )
    descripcion = models.TextField(blank=True, verbose_name=_("Descripción"))

    class Meta:
        verbose_name = _("Categoría de contacto")
        verbose_name_plural = _("Categorías de contactos")
        ordering = ["nombre"]

    def __str__(self):
        if self.parent:
            return f"{self.parent.nombre} / {self.nombre}"
        return self.nombre


class Tag(TimeStampedModel):
    """
    Etiquetas flexibles para filtrar y segmentar en la interfaz (badges/pills).
    Ejemplos: 'VIP', 'Zona Norte', 'Aparado', 'Rebajado', 'Entrega Rápida', 'Monotributista C'.
    """

    nombre = models.CharField(max_length=50, unique=True, verbose_name=_("Nombre"))
    color = models.CharField(
        max_length=7,
        default="#3B82F6",
        verbose_name=_("Color hexadecimal"),
        help_text=_(
            "Código HEX para pintar la etiqueta en el frontend. Ej: #10B981 (verde), #EF4444 (rojo)"
        ),
    )

    class Meta:
        verbose_name = _("Etiqueta (Tag)")
        verbose_name_plural = _("Etiquetas (Tags)")
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre
class TipoDocumentoAFIP(models.Model):
    """
    Tipos de Documento AFIP (80=CUIT, 86=CUIL, 96=DNI, etc.)
    """
    codigo = models.CharField(max_length=2, primary_key=True, verbose_name=_("Código AFIP"))
    descripcion = models.CharField(max_length=100, verbose_name=_("Descripción"))

    class Meta:
        verbose_name = _("Tipo de Documento AFIP")
        verbose_name_plural = _("Tipos de Documentos AFIP")
        ordering = ["codigo"]

    def __str__(self):
        return f"{self.codigo} - {self.descripcion}"


class Contacto(TimeStampedModel):
    """
    Entidad unificada para Clientes, Proveedores y Talleristas/Fasón.
    Adapta la normativa fiscal argentina (CUIT, condición IVA) y comercial.
    """

    TIPO_CHOICES = [
        ("cliente", _("Cliente")),
        ("proveedor", _("Proveedor")),
        ("fabricante", _("Fabricante")),
        ("cliente_proveedor", _("Cliente y Proveedor")),
        ("fdi_mes", _("Fideicomiso / Nodo MES (Autoridad)")),
    ]

    CONDICION_IVA_CHOICES = [
        ("responsable_inscripto", _("Responsable Inscripto")),
        ("monotributista", _("Monotributista")),
        ("exento", _("Exento")),
        ("consumidor_final", _("Consumidor Final")),
        ("no_responsable", _("No Responsable")),
    ]

    # Identificación básica
    nombre = models.CharField(max_length=200, verbose_name=_("Nombre o Razón Social"))
    codigo = models.CharField(
        max_length=20,
        unique=True,
        verbose_name=_("Código de contacto"),
        help_text=_("Ej: CLI-001, PROV-004, TAL-002"),
    )
    tipo = models.CharField(
        max_length=20,
        choices=TIPO_CHOICES,
        default="cliente",
        verbose_name=_("Tipo de relación"),
    )

    # Clasificación y Segmentación
    categoria = models.ForeignKey(
        CategoriaContacto,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="contactos",
        verbose_name=_("Categoría"),
    )
    tags = models.ManyToManyField(
        Tag, blank=True, related_name="contactos", verbose_name=_("Etiquetas")
    )

    # Datos Fiscales (Argentina)
    tipo_documento = models.ForeignKey(
        TipoDocumentoAFIP,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        verbose_name=_("Tipo de Documento"),
        help_text=_("CUIT, DNI, etc."),
    )
    cuil = models.CharField(
        max_length=13,
        blank=True,
        verbose_name=_("Número de Documento"),
        help_text=_("Sin guiones o con formato 20-XXXXXXXX-X"),
    )
    condicion_iva = models.CharField(
        max_length=30,
        choices=CONDICION_IVA_CHOICES,
        default="consumidor_final",
        verbose_name=_("Condición frente al IVA"),
    )

    # Contacto comercial
    usuario_asociado = models.OneToOneField(
        'auth.User', 
        on_delete=models.SET_NULL, 
        null=True, blank=True, 
        related_name="perfil_contacto",
        verbose_name=_("Usuario de Acceso (Portal)")
    )
    contacto_principal = models.CharField(
        max_length=200, blank=True, verbose_name=_("Persona de contacto")
    )
    telefono = models.CharField(
        max_length=50, blank=True, verbose_name=_("Teléfono / WhatsApp")
    )
    email = models.EmailField(blank=True, verbose_name=_("Email comercial"))

    # Ubicación y Logística
    direccion = models.CharField(
        max_length=300, blank=True, verbose_name=_("Dirección física / Taller")
    )
    ciudad = models.CharField(max_length=100, blank=True, verbose_name=_("Ciudad"))
    provincia = models.CharField(
        max_length=100, blank=True, verbose_name=_("Provincia")
    )
    codigo_postal = models.CharField(
        max_length=20, blank=True, verbose_name=_("Código postal")
    )

    limite_credito = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name=_("Límite de crédito en cuenta corriente"),
    )

    # Identidad y Scoring Protocolo e-OP
    es_taller_homologado = models.BooleanField(
        default=False,
        verbose_name=_("Homologado por INTI/Sindicato"),
        help_text=_("Habilita recepción de e-OPs bajo régimen RIGI/Salvataje"),
    )
    ucp_score = models.IntegerField(
        default=0,
        verbose_name=_("Unidades de Crédito Productivo (UCP)"),
        help_text=_(
            "Puntaje solidario que sube con cumplimientos y baja con defecciones (Slashing)"
        ),
    )
    clave_publica_ed25519 = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        verbose_name=_("Clave Pública Ed25519"),
        help_text=_("Para validación de firmas criptográficas en e-OPs"),
    )
    ubicacion_catastral = models.PointField(
        srid=4326,
        blank=True,
        null=True,
        verbose_name=_("Ubicación Catastral (GPS)"),
        help_text=_("Geolocalización oficial para auditoría de distancia en PoPW"),
    )

    # Estado y Notas
    activo = models.BooleanField(default=True, verbose_name=_("Activo"))
    notas = models.TextField(blank=True, verbose_name=_("Observaciones internas"))
    cbu_alias = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        verbose_name = _("Contacto")
        verbose_name_plural = _("Contactos")
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.codigo} - {self.nombre} ({self.get_tipo_display()})"
