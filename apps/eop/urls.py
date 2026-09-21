from django.urls import path
from . import views

app_name = 'eop'

urlpatterns = [
    path('contratos/', views.ContratoEOPListView.as_view(), name='contrato_list'),
    path('contratos/<int:pk>/', views.ContratoEOPDetailView.as_view(), name='contrato_detail'),
    path('contratos/<int:pk>/aceptar/', views.AceptarContratoEOPActionView.as_view(), name='contrato_aceptar'),
    path('hitos/<int:pk>/liberar/', views.LiberarHitoActionView.as_view(), name='hito_liberar'),
    path('hitos/<int:pk>/cargar_factura/', views.CargarFacturaHitoActionView.as_view(), name='hito_cargar_factura'),
    
    # Endpoints API Federada
    path('api/webhooks/mes/hito-liberado/', views.MESWebhookHitoLiberadoAPIView.as_view(), name='webhook_mes_hito_liberado'),
    path('api/webhooks/mes/contrato-fondeado/', views.MESWebhookContratoFondeadoAPIView.as_view(), name='webhook_mes_contrato_fondeado'),
]
