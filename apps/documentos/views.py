from django.shortcuts import get_object_or_404, redirect
from django.views.generic import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.http import FileResponse, Http404
from django.contrib.contenttypes.models import ContentType

from .models import DocumentoAdjunto


class DocumentoAdjuntoUploadView(LoginRequiredMixin, View):
    """
    Vista genérica para subir archivos adjuntos a cualquier objeto del sistema.
    Se invoca desde el detail view de cualquier documento (e-OP, Factura, OC, etc.)
    via un formulario que envía: archivo, nombre, descripcion, content_type_id, object_id.
    """
    def post(self, request):
        archivo = request.FILES.get("archivo")
        nombre = request.POST.get("nombre", "").strip()
        descripcion = request.POST.get("descripcion", "").strip()
        content_type_id = request.POST.get("content_type_id")
        object_id = request.POST.get("object_id")
        redirect_url = request.POST.get("redirect_url", "/")

        if not archivo or not content_type_id or not object_id:
            messages.error(request, "Faltan datos para adjuntar el archivo.")
            return redirect(redirect_url)

        try:
            ct = ContentType.objects.get(pk=content_type_id)
        except ContentType.DoesNotExist:
            messages.error(request, "Tipo de objeto inválido.")
            return redirect(redirect_url)

        try:
            DocumentoAdjunto.objects.create(
                nombre=nombre or archivo.name,
                archivo=archivo,
                descripcion=descripcion,
                content_type=ct,
                object_id=int(object_id),
                subido_por=request.user,
            )
            messages.success(request, f"Archivo '{nombre or archivo.name}' adjuntado correctamente.")
        except Exception as e:
            messages.error(request, f"Error al adjuntar el archivo: {str(e)}")

        return redirect(redirect_url)


class DocumentoAdjuntoDownloadView(LoginRequiredMixin, View):
    """
    Sirve el archivo adjunto para descarga directa.
    Usa FileResponse para transmitir el archivo sin cargarlo entero en memoria.
    """
    def get(self, request, uuid):
        doc = get_object_or_404(DocumentoAdjunto, uuid=uuid)

        try:
            response = FileResponse(
                doc.archivo.open("rb"),
                as_attachment=True,
                filename=doc.nombre,
                content_type=doc.mimetype or "application/octet-stream",
            )
            return response
        except Exception:
            raise Http404("El archivo no existe o fue eliminado.")


class DocumentoAdjuntoDeleteActionView(LoginRequiredMixin, View):
    """
    Elimina un archivo adjunto. Borra el registro y el archivo físico del disco.
    Solo el usuario que subió el archivo o un admin pueden borrarlo.
    """
    def post(self, request, uuid):
        doc = get_object_or_404(DocumentoAdjunto, uuid=uuid)
        redirect_url = request.POST.get("redirect_url", "/")

        if doc.subido_por != request.user and not request.user.is_staff:
            messages.error(request, "No tenés permiso para eliminar este archivo.")
            return redirect(redirect_url)

        nombre = doc.nombre
        doc.delete()  # El model.delete() elimina el archivo físico también
        messages.success(request, f"Archivo '{nombre}' eliminado.")
        return redirect(redirect_url)
