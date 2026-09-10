from django.urls import path
from . import views

app_name = 'tesoreria'

urlpatterns = [
    path('escrows/', views.EscrowListView.as_view(), name='escrow_list'),
    path('escrows/<int:pk>/', views.EscrowDetailView.as_view(), name='escrow_detail'),
    path('hitos/<int:pk>/liberar/', views.LiberarHitoActionView.as_view(), name='hito_liberar'),
    path('escrows/<int:pk>/fondear/', views.FondearEscrowActionView.as_view(), name='escrow_fondear'),
]
