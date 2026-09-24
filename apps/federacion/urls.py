from django.urls import path
from .views import (
    RegistroNodoView,
    RecepcionEOPView,
    RecepcionFirmaEtapaView,
    EOPWebhookReceiverAPIView,
    ParteProduccionWebhookReceiverAPIView,
    PollingNovedadesAPIView,
    TarifarioConvenioAPIView,
    PautaEscrowPublicaAPIView,
    CRLAPIView,
    BoletinOficialPublicoAPIView,
    ClearingPendientesAPIView,
    ClearingCallbackAPIView,
    ComunicacionesOficialesBuzonAPIView,
    ComunicacionOficialEnviarAPIView,
    ComunicacionOficialAcuseAPIView,
    ComunicacionOficialDetalleDescargaAPIView,
    ComunicacionOficialAdjuntarAPIView,
    ComunicacionOficialDescargarAdjuntoAPIView,
    ComunicacionOficialWebhookReceiverAPIView,
)

app_name = "federacion"

urlpatterns = [
    path("nodos/registrar/", RegistroNodoView.as_view(), name="registro_nodo"),
    path("nodos/lista/", RegistroNodoView.as_view(), name="lista_nodos"),
    path("eop/entrante/", RecepcionEOPView.as_view(), name="eop_entrante"),
    path("eop/<uuid:uuid>/firma/", RecepcionFirmaEtapaView.as_view(), name="eop_firma_etapa"),
    # ── API FEDERADA ───────────────────────────────────────────────────
    path("api/v1/novedades/", PollingNovedadesAPIView.as_view(), name="api_polling_novedades"),
    path("api/v1/eop/espejo/", EOPWebhookReceiverAPIView.as_view(), name="api_eop_espejo"),
    path("api/v1/eop/parte-produccion/", ParteProduccionWebhookReceiverAPIView.as_view(), name="api_parte_produccion"),
    # ── TARIFARIO HOMOLOGADO DE CONVENIO, PAUTA ESCROW, CRL Y BOLETÍN OFICIAL ────────
    path("api/v1/tarifario/convenio/", TarifarioConvenioAPIView.as_view(), name="api_tarifario_convenio"),
    path("api/v1/escrow/pauta/", PautaEscrowPublicaAPIView.as_view(), name="api_escrow_pauta"),
    path("api/v1/pki/crl/", CRLAPIView.as_view(), name="api_pki_crl"),
    path("api/v1/boletin/", BoletinOficialPublicoAPIView.as_view(), name="api_boletin_lista"),
    path("api/v1/boletin/<int:numero_edicion>/", BoletinOficialPublicoAPIView.as_view(), name="api_boletin_detalle"),
    # ── PORTAL FIDUCIARIO Y CLEARING BAPRO ─────────────────────────────
    path("api/v1/banco/clearing/pendientes/", ClearingPendientesAPIView.as_view(), name="api_clearing_pendientes"),
    path("api/v1/banco/clearing/confirmar/", ClearingCallbackAPIView.as_view(), name="api_clearing_confirmar"),
    # ── COMUNICACIONES OFICIALES Y CÉDULAS ELECTRÓNICAS ────────────────
    path("api/v1/comunicaciones/buzon/", ComunicacionesOficialesBuzonAPIView.as_view(), name="api_comunicaciones_buzon"),
    path("api/v1/comunicaciones/enviar/", ComunicacionOficialEnviarAPIView.as_view(), name="api_comunicaciones_enviar"),
    path("api/v1/comunicaciones/<uuid:uuid>/", ComunicacionOficialDetalleDescargaAPIView.as_view(), name="api_comunicaciones_detalle"),
    path("api/v1/comunicaciones/<uuid:uuid>/adjuntar/", ComunicacionOficialAdjuntarAPIView.as_view(), name="api_comunicaciones_adjuntar"),
    path("api/v1/comunicaciones/<uuid:uuid>/adjuntos/<uuid:adjunto_uuid>/", ComunicacionOficialDescargarAdjuntoAPIView.as_view(), name="api_comunicaciones_descargar_adjunto"),
    path("api/v1/comunicaciones/recibir/", ComunicacionOficialWebhookReceiverAPIView.as_view(), name="api_comunicaciones_recibir_webhook"),
    path("api/v1/comunicaciones/cedula/<int:cedula_id>/acuse/", ComunicacionOficialAcuseAPIView.as_view(), name="api_comunicaciones_acuse"),
]
