from django.urls import path
from .views import RegistroNodoView, RecepcionEOPView, RecepcionFirmaEtapaView

app_name = 'federacion'

urlpatterns = [
    path('nodos/registrar/', RegistroNodoView.as_view(), name='registro_nodo'),
    path('nodos/lista/', RegistroNodoView.as_view(), name='lista_nodos'),
    
    path('eop/entrante/', RecepcionEOPView.as_view(), name='eop_entrante'),
    path('eop/<uuid:uuid>/firma/', RecepcionFirmaEtapaView.as_view(), name='eop_firma_etapa'),
]
