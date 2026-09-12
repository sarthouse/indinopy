from django.urls import path
from .views import (
    RegistroNodoView,
    RecepcionEOPView,
    RecepcionFirmaEtapaView,
    EOPWebhookReceiverAPIView,
    ParteProduccionWebhookReceiverAPIView,
)

app_name = "federacion"

urlpatterns = [
    path("nodos/registrar/", RegistroNodoView.as_view(), name="registro_nodo"),
    path("nodos/lista/", RegistroNodoView.as_view(), name="lista_nodos"),
    path("eop/entrante/", RecepcionEOPView.as_view(), name="eop_entrante"),
    path(
        "eop/<uuid:uuid>/firma/",
        RecepcionFirmaEtapaView.as_view(),
        name="eop_firma_etapa",
    ),
    # ── API FEDERADA ───────────────────────────────────────────────────
    path(
        "api/v1/eop/espejo/", EOPWebhookReceiverAPIView.as_view(), name="api_eop_espejo"
    ),
    path(
        "api/v1/eop/parte-produccion/",
        ParteProduccionWebhookReceiverAPIView.as_view(),
        name="api_parte_produccion",
    ),
]
