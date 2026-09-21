from celery import shared_task
from apps.ventas.services import VentasService


@shared_task
def procesar_webhook_woo_async(tienda_id, topic, payload):
    """
    Procesa un webhook de WooCommerce de manera asíncrona dentro del adaptador.
    Libera la conexión web para que Woo no mate el webhook por timeout.
    """
    try:
        if topic in ['order.created', 'order.updated']:
            VentasService.procesar_orden_woocommerce(tienda_id, payload)

        elif topic == 'order.deleted':
            VentasService.eliminar_orden_woocommerce(tienda_id, payload)

        elif topic in ['product.created', 'product.updated']:
            VentasService.procesar_producto_woocommerce(tienda_id, payload)

        elif topic == 'product.deleted':
            VentasService.eliminar_producto_woocommerce(tienda_id, payload)

        return f"Webhook {topic} procesado exitosamente para la tienda {tienda_id}."

    except Exception as e:
        raise Exception(f"Fallo al procesar webhook {topic}: {str(e)}")
