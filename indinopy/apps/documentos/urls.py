from django.urls import path
from . import views

app_name = "documentos"

urlpatterns = [
    # ── Adjuntos Genéricos ─────────────────────────────────────────────
    path("subir/", views.DocumentoAdjuntoUploadView.as_view(), name="adjunto_upload"),
    path("<uuid:uuid>/descargar/", views.DocumentoAdjuntoDownloadView.as_view(), name="adjunto_download"),
    path("<uuid:uuid>/eliminar/", views.DocumentoAdjuntoDeleteActionView.as_view(), name="adjunto_delete"),
]
