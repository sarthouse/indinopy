from django.urls import path
from . import views

app_name = 'tesoreria'

urlpatterns = [
    path('comprobantes/', views.ComprobanteTesoreriaListView.as_view(), name='comprobante_list'),
    path('comprobantes/<int:pk>/', views.ComprobanteTesoreriaDetailView.as_view(), name='comprobante_detail'),
]
