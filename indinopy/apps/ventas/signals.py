from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.inventario.models import MovimientoStock

@receiver(post_save, sender=MovimientoStock)
def notificar_despacho_woocommerce(sender, instance, **kwargs):
    """
    Cuando un remito de salida vinculado a una Orden de Venta pasa a estado 'realizado' o 'finalizado',
    se podría disparar una tarea asíncrona para actualizar el estado en WooCommerce y pasarle el tracking.
    """
    if instance.tipo == "entrega" and instance.estado in ["realizado", "finalizado"]:
        if instance.content_type_origen and instance.content_type_origen.model == 'ordenventa':
            ov = instance.documento_origen_obj
            if ov and ov.tienda:
                # TODO: Implementar tarea Celery
                # actualizar_estado_woo_async.delay(ov.tienda_id, ov.wc_order_id, 'completed', tracking=instance.observaciones)
                pass
