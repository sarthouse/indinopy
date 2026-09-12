import uuid
from datetime import date
from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from apps.compras.models import OrdenCompra, LineaOrdenCompra
from apps.inventario.models import MovimientoStock
from apps.inventario.services import StockService

class ComprasService:
    @staticmethod
    @transaction.atomic
    def confirmar_oc(oc):
        if oc.estado != "borrador":
            return
            
        oc.estado = "confirmado"
        oc.save(update_fields=["estado"])
        
        # Este método ya asume que existe internamente, o se puede extraer aquí también.
        oc.generar_recepcion_stock()

    @staticmethod
    @transaction.atomic
    def cancelar_oc(oc):
        if oc.estado not in ["borrador", "confirmado"]:
            return
            
        oc.estado = "cancelado"
        oc.save(update_fields=["estado"])
        
        ct = ContentType.objects.get_for_model(oc)
        remitos_pendientes = MovimientoStock.objects.filter(
            content_type_origen=ct,
            object_id_origen=oc.id,
            tipo="recepcion",
            estado__in=["borrador", "confirmado"],
        )
        for remito in remitos_pendientes:
            remito.estado = "cancelado"
            remito.save(update_fields=["estado"])
            for linea in remito.lineas.filter(estado__in=["borrador", "reservado"]):
                StockService.cancelar_linea(linea)

    @staticmethod
    @transaction.atomic
    def crear_oc_borrador(proveedor, producto, cantidad, ubicacion_destino):
        """
        Crea una Orden de Compra en estado borrador generada por el MRP.
        """
        # Generar código (en producción usaría una secuencia real)
        numero_oc = f"OC-MRP-{str(uuid.uuid4())[:6].upper()}"
        
        oc = OrdenCompra.objects.create(
            numero=numero_oc,
            proveedor=proveedor,
            fecha=date.today(),
            estado="borrador",
            observaciones="Generado automáticamente por el motor MRP (Regla de Abastecimiento)."
        )
        
        # Buscar tarifa si existe
        tarifa = producto.tarifas_proveedor.filter(proveedor=proveedor).first() if hasattr(producto, 'tarifas_proveedor') else None
        precio = tarifa.precio if tarifa else 0.0
        
        LineaOrdenCompra.objects.create(
            orden=oc,
            producto=producto,
            cantidad=cantidad,
            precio_unitario=precio,
            subtotal=cantidad * precio
        )
        
        return oc
