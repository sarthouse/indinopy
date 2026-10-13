from django.urls import path
from apps.comunicaciones.views import (
    ComunicacionesOficialesBuzonAPIView,
    ComunicacionOficialEnviarAPIView,
    ComunicacionOficialAcuseAPIView,
    ComunicacionOficialDetalleDescargaAPIView,
    ComunicacionOficialAdjuntarAPIView,
    ComunicacionOficialDescargarAdjuntoAPIView,
    ComunicacionOficialWebhookReceiverAPIView,
)

app_name = "comunicaciones"

urlpatterns = [
    path("api/v1/buzon/", ComunicacionesOficialesBuzonAPIView.as_view(), name="buzon"),
    path("api/v1/enviar/", ComunicacionOficialEnviarAPIView.as_view(), name="enviar"),
    path("api/v1/<uuid:uuid>/", ComunicacionOficialDetalleDescargaAPIView.as_view(), name="detalle"),
    path("api/v1/<uuid:uuid>/adjuntar/", ComunicacionOficialAdjuntarAPIView.as_view(), name="adjuntar"),
    path("api/v1/<uuid:uuid>/adjuntos/<uuid:adjunto_uuid>/", ComunicacionOficialDescargarAdjuntoAPIView.as_view(), name="descargar_adjunto"),
    path("api/v1/recibir/", ComunicacionOficialWebhookReceiverAPIView.as_view(), name="recibir_webhook"),
    path("api/v1/cedula/<int:cedula_id>/acuse/", ComunicacionOficialAcuseAPIView.as_view(), name="acuse"),
]
