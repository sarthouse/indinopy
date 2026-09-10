import requests
from requests.auth import HTTPBasicAuth
from django.utils import timezone
from .models import TiendaWooCommerce
from .services import VentasService

class WooCommerceAPIClient:
    """
    Cliente para consumir activamente la API REST v3 de WooCommerce.
    Se utiliza como 'Fallback' (Polling) por si los Webhooks fallan.
    """
    def __init__(self, tienda_id):
        self.tienda = TiendaWooCommerce.objects.get(pk=tienda_id)
        self.base_url = f"{self.tienda.url.rstrip('/')}/wp-json/wc/v3"
        self.auth = HTTPBasicAuth(self.tienda.consumer_key, self.tienda.consumer_secret)

    def _get(self, endpoint, params=None):
        url = f"{self.base_url}/{endpoint}"
        response = requests.get(url, auth=self.auth, params=params, timeout=15)
        response.raise_for_status()
        return response.json()

    def sincronizar_ordenes_recientes(self, minutes_ago=60):
        """
        Consulta las órdenes modificadas recientemente y las sincroniza con el ERP.
        """
        after_date = (timezone.now() - timezone.timedelta(minutes=minutes_ago)).strftime('%Y-%m-%dT%H:%M:%S')
        
        params = {
            'after': after_date,
            'per_page': 100,
            'orderby': 'date',
            'order': 'asc'
        }
        
        ordenes_json = self._get('orders', params=params)
        
        resultados = {"procesadas": 0, "errores": 0}
        
        for payload in ordenes_json:
            try:
                # Reutilizamos exactamente el mismo mapeo que armamos para el Webhook
                VentasService.procesar_orden_woocommerce(self.tienda.id, payload)
                resultados["procesadas"] += 1
            except Exception as e:
                print(f"Error sincronizando orden {payload.get('id')}: {str(e)}")
                resultados["errores"] += 1
                
        return resultados

    def sincronizar_productos_modificados(self, minutes_ago=1440):
        """
        Consulta los productos modificados recientemente (ej. último día).
        """
        after_date = (timezone.now() - timezone.timedelta(minutes=minutes_ago)).strftime('%Y-%m-%dT%H:%M:%S')
        params = {'after': after_date, 'per_page': 100}
        
        productos_json = self._get('products', params=params)
        
        for payload in productos_json:
            try:
                VentasService.procesar_producto_woocommerce(self.tienda.id, payload)
            except Exception as e:
                print(f"Error sincronizando producto {payload.get('id')}: {str(e)}")
