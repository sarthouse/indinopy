from django.urls import path
from .webhooks import WooCommerceWebhookView

app_name = "integraciones_woocommerce"

urlpatterns = [
    path("webhooks/<int:tienda_id>/", WooCommerceWebhookView.as_view(), name="webhook"),
]
