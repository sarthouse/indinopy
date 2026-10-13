from django.db import transaction
from decimal import Decimal
from apps.inventario.models import StockQuant, LineaMovimientoStock, MovimientoStock

class StockService:
    @staticmethod
    def _update_quant(producto, ubicacion, lote, delta_fisica, delta_reservada):
        """
        Función utilitaria que busca el Quant (o lo crea si no existe)
        y le suma/resta las cantidades indicadas.
        """
        quant, created = StockQuant.objects.get_or_create(
            producto=producto,
            ubicacion=ubicacion,
            lote=lote,
            defaults={"cantidad_fisica": Decimal("0.0"), "cantidad_reservada": Decimal("0.0")},
        )

        quant.cantidad_fisica += Decimal(str(delta_fisica))
        quant.cantidad_reservada += Decimal(str(delta_reservada))
        quant.save()

        if quant.cantidad_fisica == 0 and quant.cantidad_reservada == 0:
            quant.delete()

    @staticmethod
    @transaction.atomic
    def reservar_linea(linea):
        """Pasa una línea a estado reservado y compromete el stock."""
        if linea.estado == "reservado":
            return
        
        linea.estado = "reservado"
        linea.save(update_fields=["estado"])
        
        qty = linea.cantidad  # BUG FIX: Reservar lo planeado, no lo hecho
        StockService._update_quant(
            linea.producto, 
            linea.ubicacion_origen, 
            linea.lote, 
            delta_fisica=0, 
            delta_reservada=qty
        )

    @staticmethod
    @transaction.atomic
    def realizar_linea(linea, estado_viejo=None):
        """Pasa una línea a estado realizado, moviendo físicamente el stock."""
        if linea.estado == "realizado" and estado_viejo == "realizado":
            return
        
        estado_anterior = estado_viejo or linea.estado
        linea.estado = "realizado"
        linea.save(update_fields=["estado"])
        
        qty = linea.cantidad_hecha
        
        # Si venía de reservado, liberamos la reserva primero
        if estado_anterior == "reservado":
            StockService._update_quant(linea.producto, linea.ubicacion_origen, linea.lote, delta_fisica=0, delta_reservada=-linea.cantidad)
            
        # Descuenta el físico del origen
        StockService._update_quant(linea.producto, linea.ubicacion_origen, linea.lote, delta_fisica=-qty, delta_reservada=0)
        
        # Aumenta el físico del destino
        StockService._update_quant(linea.producto, linea.ubicacion_destino, linea.lote, delta_fisica=qty, delta_reservada=0)


    @staticmethod
    @transaction.atomic
    def cancelar_linea(linea, estado_viejo=None):
        estado_anterior = estado_viejo or linea.estado
        if estado_anterior == "cancelado":
            return
        
        linea.estado = "cancelado"
        linea.save(update_fields=["estado"])
        qty = linea.cantidad_hecha
        
        if estado_anterior == "reservado":
            StockService._update_quant(linea.producto, linea.ubicacion_origen, linea.lote, delta_fisica=0, delta_reservada=-qty)
        elif estado_anterior == "realizado":
            StockService._update_quant(linea.producto, linea.ubicacion_origen, linea.lote, delta_fisica=qty, delta_reservada=0)
            StockService._update_quant(linea.producto, linea.ubicacion_destino, linea.lote, delta_fisica=-qty, delta_reservada=0)
