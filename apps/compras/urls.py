from django.urls import path
from . import views

app_name = 'compras'

urlpatterns = [
    path('ordenes/', views.OrdenCompraListView.as_view(), name='oc_list'),
    path('ordenes/<int:pk>/', views.OrdenCompraDetailView.as_view(), name='oc_detail'),
    path('ordenes/<int:pk>/confirmar/', views.ConfirmarOCActionView.as_view(), name='oc_confirmar'),
    path('ordenes/<int:pk>/cancelar/', views.CancelarOCActionView.as_view(), name='oc_cancelar'),
]
