from django.db import transaction
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
        defaults={"cantidad_fisica": 0.0, "cantidad_reservada": 0.0},
    )

    quant.cantidad_fisica += delta_fisica
    quant.cantidad_reservada += delta_reservada
    quant.save()

    # (Opcional) Limpieza: Si el quant quedó en 0 físico y 0 reservado, se podría borrar para ahorrar espacio en BD.
    if quant.cantidad_fisica == 0 and quant.cantidad_reservada == 0:
        quant.delete()


@receiver(post_save, sender=LineaMovimientoStock)
def procesar_movimiento_stock(sender, instance, created, **kwargs):
    """
    Motor principal que reacciona a los cambios de estado del Movimiento
    y actualiza los Quants en las ubicaciones correspondientes.
    """
    estado_viejo = getattr(instance, "_original_estado", None)
    estado_nuevo = instance.estado

    # Si el estado no cambió, no hacemos nada (ej. solo le cambiaron la fecha o una nota)
    if estado_viejo == estado_nuevo:
        return

    with transaction.atomic():
        qty = (
            instance.cantidad_hecha
        )  # FIX LÓGICO: usar cantidad_hecha en vez de cantidad pedida
        prod = instance.producto
        lote = instance.lote
        origen = instance.ubicacion_origen
        destino = instance.ubicacion_destino

        # 1. PASA A RESERVADO
        if estado_nuevo == "reservado":
            # La reserva SOLO afecta a la ubicación de origen (comprometemos el stock para que no se venda a otro)
            _update_quant(prod, origen, lote, delta_fisica=0, delta_reservada=qty)

        # 2. PASA A REALIZADO
        elif estado_nuevo == "realizado":
            # A) Restamos el físico del Origen
            _update_quant(prod, origen, lote, delta_fisica=-qty, delta_reservada=0)

            # B) Sumamos el físico al Destino
            _update_quant(prod, destino, lote, delta_fisica=qty, delta_reservada=0)

            # C) Si venía de estar 'reservado', tenemos que "liberar" esa reserva del Origen
            # porque ya se concretó la salida física.
            if estado_viejo == "reservado":
                _update_quant(prod, origen, lote, delta_fisica=0, delta_reservada=-qty)

        # 3. CANCELADO
        elif estado_nuevo == "cancelado":
            if estado_viejo == "reservado":
                _update_quant(prod, origen, lote, delta_fisica=0, delta_reservada=-qty)
            elif estado_viejo == "realizado":
                _update_quant(prod, origen, lote, delta_fisica=qty, delta_reservada=0)
                _update_quant(prod, destino, lote, delta_fisica=-qty, delta_reservada=0)

    # Actualizamos el original estado post-save
    instance._original_estado = estado_nuevo


from django.db.models.signals import post_migrate


@receiver(post_migrate)
def crear_unidades_medida_por_defecto(sender, **kwargs):
    """Crea las unidades de medida base del sistema industrial al migrar."""
    if sender.name == "apps.inventario":
        from .models import UnidadMedida

        unidades_defecto = [
            {"nombre": "Unidades", "simbolo": "u", "tipo": "unidad"},
            {"nombre": "Pares", "simbolo": "par", "tipo": "unidad"},
            {"nombre": "Metros", "simbolo": "m", "tipo": "longitud"},
            {"nombre": "Centímetros", "simbolo": "cm", "tipo": "longitud"},
            {"nombre": "Kilogramos", "simbolo": "kg", "tipo": "peso"},
            {"nombre": "Gramos", "simbolo": "g", "tipo": "peso"},
            {"nombre": "Litros", "simbolo": "l", "tipo": "volumen"},
            {"nombre": "Horas", "simbolo": "hs", "tipo": "tiempo"},
            {"nombre": "Minutos", "simbolo": "min", "tipo": "tiempo"},
        ]

        for u in unidades_defecto:
            UnidadMedida.objects.get_or_create(
                simbolo=u["simbolo"],
                defaults={"nombre": u["nombre"], "tipo": u["tipo"], "activa": True},
            )
