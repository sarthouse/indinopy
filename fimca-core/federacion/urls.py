from django.urls import path
from .views import (
    RegistroNodoView,
    RecepcionEOPView,
    RecepcionFirmaEtapaView,
    PollingNovedadesAPIView,
    TarifarioConvenioAPIView,
    PautaEscrowPublicaAPIView,
    CRLAPIView,
    BoletinOficialPublicoAPIView,
    ClearingPendientesAPIView,
    ClearingCallbackAPIView,
)

app_name = "federacion"

urlpatterns = [
    path("nodos/registrar/", RegistroNodoView.as_view(), name="registro_nodo"),
    path("nodos/lista/", RegistroNodoView.as_view(), name="lista_nodos"),
    path("eop/entrante/", RecepcionEOPView.as_view(), name="eop_entrante"),
    path("eop/<uuid:uuid>/firma/", RecepcionFirmaEtapaView.as_view(), name="eop_firma_etapa"),
    # ── API FEDERADA ───────────────────────────────────────────────────
    path("api/v1/novedades/", PollingNovedadesAPIView.as_view(), name="api_polling_novedades"),
    # ── TARIFARIO HOMOLOGADO DE CONVENIO, PAUTA ESCROW, CRL Y BOLETÍN OFICIAL ────────
    path("api/v1/tarifario/convenio/", TarifarioConvenioAPIView.as_view(), name="api_tarifario_convenio"),
    path("api/v1/escrow/pauta/", PautaEscrowPublicaAPIView.as_view(), name="api_escrow_pauta"),
    path("api/v1/pki/crl/", CRLAPIView.as_view(), name="api_pki_crl"),
    path("api/v1/boletin/", BoletinOficialPublicoAPIView.as_view(), name="api_boletin_lista"),
    path("api/v1/boletin/<int:numero_edicion>/", BoletinOficialPublicoAPIView.as_view(), name="api_boletin_detalle"),
    # ── PORTAL FIDUCIARIO Y CLEARING BAPRO ─────────────────────────────
    path("api/v1/banco/clearing/pendientes/", ClearingPendientesAPIView.as_view(), name="api_clearing_pendientes"),
    path("api/v1/banco/clearing/confirmar/", ClearingCallbackAPIView.as_view(), name="api_clearing_confirmar"),
]

