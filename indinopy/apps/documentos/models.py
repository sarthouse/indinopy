import uuid
import os
import mimetypes

from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from apps.base.models import TimeStampedModel


MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB

ALLOWED_MIMETYPES = [
    "application/pdf",
    "application/json",
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]

ALLOWED_EXTENSIONS = [
    ".pdf",
    ".json",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".xls",
    ".xlsx",
    ".doc",
    ".docx",
]


def _ruta_adjunto(instance, filename):
    """Genera ruta limpia: media/adjuntos/{app}/{model}/{id}/{uuid}_{filename}"""
    ext = os.path.splitext(filename)[1].lower()
    uuid_name = f"{instance.uuid}{ext}"
    return os.path.join(
        "adjuntos",
        instance.res_model.replace(".", os.sep),
        str(instance.res_id),
        uuid_name,
    )


class DocumentoAdjunto(TimeStampedModel):
    """
    Archivo adjunto genérico vinculado a cualquier documento del sistema
    (Remito, Orden de Producción, Factura, Ficha Técnica, etc.) mediante GenericForeignKey.
    """

    uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    nombre = models.CharField(max_length=255, verbose_name=_("Nombre del archivo"))
    archivo = models.FileField(
        upload_to=_ruta_adjunto,
        verbose_name=_("Archivo"),
    )
    mimetype = models.CharField(max_length=100, blank=True, verbose_name=_("Tipo MIME"))
    tamano = models.PositiveIntegerField(default=0, verbose_name=_("Tamaño (bytes)"))
    descripcion = models.TextField(blank=True, verbose_name=_("Descripción"))

    # GenericForeignKey de Django
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="+",
    )
    object_id = models.PositiveIntegerField()
    contenido_objeto = GenericForeignKey("content_type", "object_id")

    # Campos auxiliares para indexación y ruta de almacenamiento
    res_model = models.CharField(max_length=100, editable=False)
    res_id = models.PositiveIntegerField(editable=False)

    subido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="documentos_subidos",
        verbose_name=_("Subido por"),
    )

    class Meta:
        ordering = ["-creado_en"]
        verbose_name = _("Documento adjunto")
        verbose_name_plural = _("Documentos adjuntos")
        indexes = [
            models.Index(fields=["res_model", "res_id"]),
        ]

    def __str__(self):
        return f"{self.nombre} ({self.res_model} #{self.res_id})"

    def save(self, *args, **kwargs):
        """Auto-detecta mimetype y tamaño, sincroniza res_model/res_id."""
        if self.archivo:
            if not self.mimetype:
                self.mimetype, _ = mimetypes.guess_type(self.archivo.name)
                if not self.mimetype:
                    self.mimetype = "application/octet-stream"
            if not self.tamano:
                try:
                    self.tamano = self.archivo.size
                except Exception:
                    pass

        if self.content_type:
            self.res_model = f"{self.content_type.app_label}.{self.content_type.model}"
        if self.object_id:
            self.res_id = self.object_id

        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        self._validar_tamano()
        self._validar_tipo()
        self._validar_nombre_duplicado()

    def _validar_tamano(self):
        if self.archivo and self.archivo.size > MAX_FILE_SIZE:
            raise ValidationError(
                {
                    "archivo": _(
                        f"El archivo excede el tamaño máximo de {MAX_FILE_SIZE // (1024 * 1024)}MB"
                    )
                }
            )

    def _validar_tipo(self):
        if not self.archivo:
            return
        ext = os.path.splitext(self.archivo.name)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValidationError(
                {
                    "archivo": _(
                        f"Tipo de archivo no permitido: {ext}. Permitidos: PDF, imágenes, Excel, Word"
                    )
                }
            )

    def _validar_nombre_duplicado(self):
        if not self.content_type_id or not self.object_id:
            return
        qs = DocumentoAdjunto.objects.filter(
            content_type_id=self.content_type_id,
            object_id=self.object_id,
            nombre=self.nombre,
        )
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        if qs.exists():
            raise ValidationError(
                {
                    "nombre": _(
                        f'Ya existe un archivo con el nombre "{self.nombre}" adjunto a este registro'
                    )
                }
            )

    @property
    def extension(self):
        if self.archivo:
            return os.path.splitext(self.archivo.name)[1].lower()
        return ""

    @property
    def es_imagen(self):
        return self.mimetype.startswith("image/") if self.mimetype else False

    @property
    def es_pdf(self):
        return self.mimetype == "application/pdf"

    @property
    def tamano_formateado(self):
        if self.tamano < 1024:
            return f"{self.tamano} B"
        elif self.tamano < 1024 * 1024:
            return f"{self.tamano / 1024:.1f} KB"
        else:
            return f"{self.tamano / (1024 * 1024):.1f} MB"

    def delete(self, *args, **kwargs):
        """Elimina el archivo físico del disco al borrar el registro."""
        if self.archivo:
            try:
                self.archivo.delete(save=False)
            except Exception:
                pass
        super().delete(*args, **kwargs)
