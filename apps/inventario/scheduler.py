import logging
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum

from apps.inventario.models import Producto, ReglaAbastecimiento, Ubicacion, StockQuant
from apps.inventario.services import StockService

# Intentar importar servicios de otros módulos para crear borradores
try:
    from apps.compras.services import ComprasService
except ImportError:
    ComprasService = None

try:
    from apps.produccion.services import ProduccionService
except ImportError:
    ProduccionService = None

logger = logging.getLogger(__name__)


class SchedulerAbastecimientoService:
    """
    Motor de Planificación (MRP Scheduler).
    Evalúa el Stock Virtual (Proyectado) contra las Reglas de Abastecimiento (MTS).
    """

    @staticmethod
    def _calcular_stock_virtual(producto_id, ubicacion_id):
        """
        Calcula: Físico - Reservado Duro + Entradas Esperadas.
        Por simplicidad actual: Físico - Reservado. 
        En el futuro: sumar Movimientos de Recepción en estado 'borrador/confirmado'.
        """
        # Obtenemos los quants físicos y reservados en la ubicación exacta y sus hijas
        quants = StockQuant.objects.filter(
            producto_id=producto_id, 
            ubicacion_id=ubicacion_id
        ).aggregate(
            total_fisico=Sum('cantidad_fisica'),
            total_reservado=Sum('cantidad_reservada')
        )
        
        fisico = quants['total_fisico'] or Decimal('0.00')
        reservado = quants['total_reservado'] or Decimal('0.00')
        
        # Virtual = Lo que tengo - Lo que ya prometí a otra orden
        return fisico - reservado

    @staticmethod
    def _calcular_cantidad_a_pedir(stock_virtual, regla):
        """
        Aplica la matemática del ROP y Múltiplos (EOQ adaptado).
        """
        if stock_virtual >= regla.cantidad_minima:
            return Decimal('0.00')
            
        faltante = regla.cantidad_maxima - stock_virtual
        
        # Ajustar según el múltiplo de pedido (ej: cajas de 50)
        multiplo = regla.multiplo_pedido
        if multiplo > 0 and faltante % multiplo != 0:
            # Redondear hacia arriba al múltiplo más cercano
            faltante = ((faltante // multiplo) + 1) * multiplo
            
        return faltante

    @staticmethod
    @transaction.atomic
    def ejecutar_planificador():
        """
        Punto de entrada principal. Recorre todas las reglas activas.
        En producción, este método debería encolarse en Celery (por ubicación/almacén)
        para no bloquear la base de datos entera.
        """
        logger.info("Iniciando Scheduler de Abastecimiento MRP...")
        reglas = ReglaAbastecimiento.objects.filter(activa=True).select_related('producto', 'ubicacion')
        
        compras_generadas = 0
        producciones_generadas = 0
        
        for regla in reglas:
            stock_virtual = SchedulerAbastecimientoService._calcular_stock_virtual(
                regla.producto.id, 
                regla.ubicacion.id
            )
            
            qty_pedir = SchedulerAbastecimientoService._calcular_cantidad_a_pedir(stock_virtual, regla)
            
            if qty_pedir > 0:
                logger.info(f"Ruptura de stock detectada para {regla.producto.nombre} en {regla.ubicacion.nombre}. Faltante: {qty_pedir}")
                
                if regla.tipo_ruta == 'comprar':
                    if ComprasService:
                        # Buscamos el proveedor principal o TarifaProveedor
                        tarifa = regla.producto.tarifas_proveedor.order_by('precio').first() if hasattr(regla.producto, 'tarifas_proveedor') else None
                        proveedor = tarifa.proveedor if tarifa else None
                        
                        if proveedor:
                            # Se generaría un borrador de OC (Draft PO)
                            ComprasService.crear_oc_borrador(proveedor, regla.producto, qty_pedir, regla.ubicacion)
                            compras_generadas += 1
                        else:
                            logger.warning(f"No hay proveedor configurado para comprar {regla.producto.nombre}.")
                            
                elif regla.tipo_ruta == 'fabricar':
                    if ProduccionService:
                        # Se generaría un borrador de Orden de Producción (Draft MO)
                        ProduccionService.crear_op_borrador(regla.producto, qty_pedir, regla.ubicacion)
                        producciones_generadas += 1
                        
                elif regla.tipo_ruta == 'transferir':
                    # Lógica de reabastecimiento entre almacenes locales (Inter-Warehouse Push/Pull)
                    pass
                    
        logger.info(f"Scheduler finalizado. OCs Borrador: {compras_generadas}, OPs Borrador: {producciones_generadas}")
        return {
            "compras": compras_generadas,
            "producciones": producciones_generadas
        }
