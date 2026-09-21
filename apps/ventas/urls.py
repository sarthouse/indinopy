from django.urls import path
from . import views
from apps.integraciones.woocommerce.webhooks import WooCommerceWebhookView

app_name = 'ventas'

urlpatterns = [
    path('ordenes/', views.OrdenVentaListView.as_view(), name='ov_list'),
    path('ordenes/<int:pk>/', views.OrdenVentaDetailView.as_view(), name='ov_detail'),
    path('ordenes/<int:pk>/pdf/', views.PresupuestoPDFDownloadView.as_view(), name='ov_pdf'),
    path('ordenes/<int:pk>/confirmar/', views.ConfirmarOVActionView.as_view(), name='ov_confirmar'),
    
    # Webhook Endpoint (Mantenido por compatibilidad de URL con reenvío al adaptador)
    path('webhooks/woocommerce/<int:tienda_id>/', WooCommerceWebhookView.as_view(), name='woo_webhook'),
]
