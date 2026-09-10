from django.urls import path
from . import views

app_name = 'contabilidad'

urlpatterns = [
    path('facturas/', views.DocumentoDeudaListView.as_view(), name='factura_list'),
    path('facturas/<int:pk>/', views.DocumentoDeudaDetailView.as_view(), name='factura_detail'),
    path('facturas/<int:pk>/emitir/', views.EmitirAFIPActionView.as_view(), name='factura_emitir'),
]
