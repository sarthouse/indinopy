import hmac
import hashlib
import base64
import json
from django.http import HttpResponse, JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404
from .models import TiendaWooCommerce
from .services import VentasService

@method_decorator(csrf_exempt, name='dispatch')
class WooCommerceWebhookView(View):
    """
    Endpoint único para recibir todos los webhooks de una tienda WooCommerce.
    Valida la firma HMAC y delega a la capa de servicios según el tópico.
    """
    def post(self, request, tienda_id):
        tienda = get_object_or_404(TiendaWooCommerce, pk=tienda_id, activa=True)
        
        # 1. Validación de Firma Criptográfica (Seguridad Obligatoria)
        signature_header = request.headers.get('x-wc-webhook-signature')
        if not signature_header:
            return HttpResponse("Firma ausente", status=401)
            
        raw_body = request.body
        computed_signature = base64.b64encode(
            hmac.new(
                key=tienda.webhook_secret.encode('utf-8'),
                msg=raw_body,
                digestmod=hashlib.sha256
            ).digest()
        ).decode('utf-8')
        
        if not hmac.compare_digest(computed_signature, signature_header):
            return HttpResponse("Firma inválida", status=401)

        # 2. Ruteo según el Tópico del Webhook
        topic = request.headers.get('x-wc-webhook-topic', '')
        
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            return HttpResponse("Payload inválido", status=400)

        # Procesamiento asincrónico vía Celery
        from .tasks import procesar_webhook_woo_async
        procesar_webhook_woo_async.delay(tienda.id, topic, payload)
        
        # WooCommerce exige un HTTP 200 rápido para no deshabilitar el Webhook
        return JsonResponse({"status": "encolado", "topic": topic})
