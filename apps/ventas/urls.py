from django.urls import path
from . import views
from .webhooks import WooCommerceWebhookView

app_name = 'ventas'

urlpatterns = [
    path('ordenes/', views.OrdenVentaListView.as_view(), name='ov_list'),
    path('ordenes/<int:pk>/', views.OrdenVentaDetailView.as_view(), name='ov_detail'),
    path('ordenes/<int:pk>/confirmar/', views.ConfirmarOVActionView.as_view(), name='ov_confirmar'),
    
    # Webhook Endpoint
    path('webhooks/woocommerce/<int:tienda_id>/', WooCommerceWebhookView.as_view(), name='woo_webhook'),
]
