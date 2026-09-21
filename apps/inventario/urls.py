from django.urls import path
from . import views

app_name = 'inventario'

urlpatterns = [
    path('quants/', views.StockQuantListView.as_view(), name='quant_list'),
    path('movimientos/', views.MovimientoStockListView.as_view(), name='movimiento_list'),
    path('movimientos/<int:pk>/', views.MovimientoStockDetailView.as_view(), name='movimiento_detail'),
    path('movimientos/<int:pk>/remito/', views.RemitoPDFDownloadView.as_view(), name='remito_pdf'),
    path('lineas/<int:pk>/realizar/', views.RealizarLineaActionView.as_view(), name='linea_realizar'),

    # Reportes Tabulares (Excel / CSV)
    path('reportes/inventario-stock/', views.InventarioStockExportView.as_view(), name='inventario_stock_report'),
    path('reportes/movimientos-stock/', views.MovimientosStockExportView.as_view(), name='movimientos_stock_report'),
]
