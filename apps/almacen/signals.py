from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from .models import LineaMovimientoStock, StockQuant

def _update_quant(producto, ubicacion, lote, delta_fisica, delta_reservada):
    """
    Función utilitaria que busca el Quant (o lo crea si no existe)
    y le suma/resta las cantidades indicadas.
    """
    # get_or_create es magia: si el producto jamás estuvo en esta ubicación, crea el registro en cero.
    quant, created = StockQuant.objects.get_or_create(
        producto=producto,
        ubicacion=ubicacion,
        lote=lote,
        defaults={'cantidad_fisica': 0.0, 'cantidad_reservada': 0.0}
    )
    
    quant.cantidad_fisica += delta_fisica
    quant.cantidad_reservada += delta_reservada
    quant.save()

    # (Opcional) Limpieza: Si el quant quedó en 0 físico y 0 reservado, se podría borrar para ahorrar espacio en BD.
    if quant.cantidad_fisica == 0 and quant.cantidad_reservada == 0:
        quant.delete()


@receiver(pre_save, sender=LineaMovimientoStock)
def capturar_estado_anterior(sender, instance, **kwargs):
    """
    Antes de guardar el movimiento, guardamos su estado anterior en un atributo temporal.
    Esto nos permite saber si pasó de 'reservado' a 'realizado', por ejemplo.
    """
    if instance.pk:
        old_instance = LineaMovimientoStock.objects.get(pk=instance.pk)
        instance._old_estado = old_instance.estado
    else:
        instance._old_estado = None


@receiver(post_save, sender=LineaMovimientoStock)
def procesar_movimiento_stock(sender, instance, created, **kwargs):
    """
    Motor principal que reacciona a los cambios de estado del Movimiento
    y actualiza los Quants en las ubicaciones correspondientes.
    """
    estado_viejo = getattr(instance, '_old_estado', None)
    estado_nuevo = instance.estado

    # Si el estado no cambió, no hacemos nada (ej. solo le cambiaron la fecha o una nota)
    if estado_viejo == estado_nuevo:
        return

    qty = instance.cantidad
    prod = instance.producto
    lote = instance.lote
    origen = instance.ubicacion_origen
    destino = instance.ubicacion_destino

    # 1. PASA A RESERVADO
    if estado_nuevo == 'reservado':
        # La reserva SOLO afecta a la ubicación de origen (comprometemos el stock para que no se venda a otro)
        _update_quant(prod, origen, lote, delta_fisica=0, delta_reservada=qty)

    # 2. PASA A REALIZADO
    elif estado_nuevo == 'realizado':
        # A) Restamos el físico del Origen
        _update_quant(prod, origen, lote, delta_fisica=-qty, delta_reservada=0)
        
        # B) Sumamos el físico al Destino
        _update_quant(prod, destino, lote, delta_fisica=qty, delta_reservada=0)
        
        # C) Si venía de estar 'reservado', tenemos que "liberar" esa reserva del Origen 
        # porque ya se concretó la salida física.
        if estado_viejo == 'reservado':
            _update_quant(prod, origen, lote, delta_fisica=0, delta_reservada=-qty)

    # 3. CANCELADO
    elif estado_nuevo == 'cancelado':
        # Si estaba reservado y se canceló la OP, simplemente liberamos la reserva del Origen
        if estado_viejo == 'reservado':
            _update_quant(prod, origen, lote, delta_fisica=0, delta_reservada=-qty)
        
        # Si ya estaba realizado y se canceló (ej. error humano), tenemos que revertir el movimiento físico
        elif estado_viejo == 'realizado':
            _update_quant(prod, origen, lote, delta_fisica=qty, delta_reservada=0)
            _update_quant(prod, destino, lote, delta_fisica=-qty, delta_reservada=0)

