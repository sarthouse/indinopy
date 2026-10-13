from django.urls import path
from . import views

app_name = 'contabilidad'

urlpatterns = [
    path('facturas/', views.DocumentoDeudaListView.as_view(), name='factura_list'),
    path('facturas/<int:pk>/', views.DocumentoDeudaDetailView.as_view(), name='factura_detail'),
    path('facturas/<int:pk>/pdf/', views.ComprobantePDFDownloadView.as_view(), name='factura_pdf'),
    path('facturas/<int:pk>/emitir/', views.EmitirAFIPActionView.as_view(), name='factura_emitir'),
    path('reportes/libro-iva-ventas/', views.LibroIVAVentasExportView.as_view(), name='libro_iva_ventas_export'),
    path('reportes/libro-iva-compras/', views.LibroIVAComprasExportView.as_view(), name='libro_iva_compras_export'),
    path('reportes/convenio-multilateral/', views.ConvenioMultilateralExportView.as_view(), name='convenio_multilateral_export'),
]


