from django.urls import path
from . import views

app_name = 'contactos'

urlpatterns = [
    path('', views.ContactoListView.as_view(), name='contacto_list'),
    path('<int:pk>/', views.ContactoDetailView.as_view(), name='contacto_detail'),
    path('nuevo/', views.ContactoCreateView.as_view(), name='contacto_create'),
    path('<int:pk>/editar/', views.ContactoUpdateView.as_view(), name='contacto_update'),
]
