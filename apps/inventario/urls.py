from django.urls import path
from . import views

app_name = 'inventario'

urlpatterns = [
    path('quants/', views.StockQuantListView.as_view(), name='quant_list'),
    path('movimientos/', views.MovimientoStockListView.as_view(), name='movimiento_list'),
    path('movimientos/<int:pk>/', views.MovimientoStockDetailView.as_view(), name='movimiento_detail'),
    path('lineas/<int:pk>/realizar/', views.RealizarLineaActionView.as_view(), name='linea_realizar'),
]
