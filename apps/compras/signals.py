from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import OrdenCompra

@receiver(post_save, sender="inventario.MovimientoStock")
def sincronizar_recepcion_stock_con_oc(sender, instance, **kwargs):
    """
    Cuando un MovimientoStock de tipo 'recepcion' se guarda (especialmente al pasar a 'finalizado'
    o dividirse en backorder), sincroniza las cantidades recibidas en la Orden de Compra origen.
    """
    if instance.tipo == "recepcion" and instance.content_type_origen:
        if isinstance(instance.documento_origen_obj, OrdenCompra):
            instance.documento_origen_obj.actualizar_cantidades_recibidas()


@receiver(post_save, sender="inventario.LineaMovimientoStock")
def sincronizar_linea_stock_con_oc(sender, instance, **kwargs):
    """
    Si una línea de recepción cambia a 'realizado', actualiza las cantidades recibidas de la OC.
    """
    if (
        getattr(instance, "movimiento", None)
        and instance.movimiento.tipo == "recepcion"
        and instance.movimiento.content_type_origen
    ):
        if instance.estado == "realizado":
            oc = instance.movimiento.documento_origen_obj
            if isinstance(oc, OrdenCompra):
                oc.actualizar_cantidades_recibidas()
