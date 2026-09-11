from django.urls import path
from . import views

app_name = 'nomina'

urlpatterns = [
    # Reportes
    path('exportar-lsd/<int:anio>/<int:mes>/', views.exportar_lsd_csv, name='exportar_lsd_csv'),
    path('recibo/<int:pk>/', views.imprimir_recibo, name='imprimir_recibo'),
    
    # Empleados
    path('empleados/', views.EmpleadoListView.as_view(), name='empleado_list'),
    path('empleados/<int:pk>/', views.EmpleadoDetailView.as_view(), name='empleado_detail'),
    path('empleados/<int:pk>/egreso/', views.EmpleadoEgresoView.as_view(), name='empleado_egreso'),
]
