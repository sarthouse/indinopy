from django.urls import path
from . import views
from . import api_views

app_name = 'produccion'

urlpatterns = [
    path('ops/', views.OPListView.as_view(), name='op_list'),
    path('ops/<int:pk>/', views.OPDetailView.as_view(), name='op_detail'),
    path('ops/<int:pk>/confirmar/', views.OPConfirmarActionView.as_view(), name='op_confirmar'),
    path('ops/<int:pk>/finalizar/', views.OPFinalizarActionView.as_view(), name='op_finalizar'),
    path('ops/<int:pk>/cancelar/', views.OPCancelarActionView.as_view(), name='op_cancelar'),
    
    # API Headless (Gateway Externo)
    path('api/v1/headless/e-op/', api_views.RecepcionHeadlessEOPView.as_view(), name='api_headless_eop'),
]
