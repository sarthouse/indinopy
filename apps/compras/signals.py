from decimal import Decimal
from django.db import transaction
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from .models import OrdenCompra
from apps.inventario.models import MovimientoStock, LineaMovimientoStock


@receiver(pre_save, sender=OrdenCompra)
def capturar_estado_anterior_oc(sender, instance, **kwargs):
    """Guarda el estado anterior de la Orden de Compra para detectar transiciones."""
    if instance.pk:
        old = OrdenCompra.objects.filter(pk=instance.pk).values("estado").first()
        instance._old_estado = old["estado"] if old else None
    else:
        instance._old_estado = None


@receiver(post_save, sender=OrdenCompra)
def procesar_transicion_estado_oc(sender, instance, created, **kwargs):
    """
    Gestiona los efectos secundarios automáticos al cambiar de estado una Orden de Compra.
    - Al pasar a 'confirmado': genera el MovimientoStock de recepción entrante en Almacén.
    - Al pasar a 'cancelado': cancela remitos pendientes asociados.
    """
    estado_viejo = getattr(instance, "_old_estado", None)
    estado_nuevo = instance.estado

    if estado_viejo == estado_nuevo:
        return

    # A) BORRADOR -> CONFIRMADO: Generar remito de recepción
    if estado_nuevo == "confirmado":
        with transaction.atomic():
            instance.generar_recepcion_stock()

    # B) -> CANCELADO: Cancelar remitos entrantes no ejecutados
    elif estado_nuevo == "cancelado":
        with transaction.atomic():
            remitos_pendientes = MovimientoStock.objects.filter(
                documento_origen=instance.numero,
                tipo="recepcion",
                estado__in=["borrador", "confirmado"],
            )
            for remito in remitos_pendientes:
                remito.estado = "cancelado"
                remito.save()
                for linea in remito.lineas.filter(estado__in=["borrador", "reservado"]):
                    linea.estado = "cancelado"
                    linea.save()


@receiver(post_save, sender=MovimientoStock)
def sincronizar_recepcion_stock_con_oc(sender, instance, **kwargs):
    """
    Cuando un MovimientoStock de tipo 'recepcion' se guarda (especialmente al pasar a 'finalizado'
    o dividirse en backorder), sincroniza las cantidades recibidas en la Orden de Compra origen.
    """
    if instance.tipo == "recepcion" and instance.documento_origen:
        oc = OrdenCompra.objects.filter(numero=instance.documento_origen).first()
        if oc:
            oc.actualizar_cantidades_recibidas()


@receiver(post_save, sender=LineaMovimientoStock)
def sincronizar_linea_stock_con_oc(sender, instance, **kwargs):
    """
    Si una línea de recepción cambia a 'realizado', actualiza las cantidades recibidas de la OC.
    """
    if instance.movimiento and instance.movimiento.tipo == "recepcion" and instance.movimiento.documento_origen:
        if instance.estado == "realizado":
            oc = OrdenCompra.objects.filter(numero=instance.movimiento.documento_origen).first()
            if oc:
                oc.actualizar_cantidades_recibidas()
