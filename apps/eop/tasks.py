import logging
from celery import shared_task
from apps.eop.models import EOPHitoEscrow
from apps.eop.services import EOPService

logger = logging.getLogger(__name__)

@shared_task
def constatar_facturas_arca_pendientes():
    """
    Cronjob (ej: nocturno) que busca todos los hitos en estado 'fiscal_pending'.
    Por cada uno, consulta a la API de ARCA para verificar si el tallerista
    ya emitió la factura. Si la encuentra, guarda el CAE y destraba los fondos.
    """
    hitos_pendientes = EOPHitoEscrow.objects.filter(estado="fiscal_pending")
    
    if not hitos_pendientes.exists():
        logger.info("No hay hitos en retención FISCAL_PENDING.")
        return "0 procesados"

    procesados = 0
    liberados = 0

    for hito in hitos_pendientes:
        procesados += 1
        
        # 1. Obtener CUITs
        # Asumimos que el contrato tiene el tallerista asignado
        op = hito.contrato.orden_produccion_local
        tallerista_cuit = None
        if op and hasattr(op, "tallerista_principal") and op.tallerista_principal:
            tallerista_cuit = op.tallerista_principal.cuil
        elif "tallerista" in (hito.contrato.firmas_digitales or {}):
            tallerista_cuit = hito.contrato.firmas_digitales["tallerista"].get("cuit")

        if not tallerista_cuit:
            continue
            
        monto_requerido = (hito.contrato.monto_total_uci * hito.porcentaje_tramo) / 100
        
        # 2. Consultar al servicio de AFIP/ARCA (Mock / Adapter)
        # En una implementación real, importaríamos apps.contabilidad.utils.FacturadorAFIP
        # y buscaríamos facturas emitidas por `tallerista_cuit` a nuestro CUIT por `monto_requerido`.
        factura_encontrada = _mock_consultar_arca(tallerista_cuit, monto_requerido)
        
        if factura_encontrada:
            # 3. Guardar el CAE y liberar
            hito.factura_asociada_arca = factura_encontrada["cae"]
            hito.save(update_fields=["factura_asociada_arca"])
            
            try:
                EOPService.liberar_hito(hito.pk)
                liberados += 1
                logger.info(f"Hito {hito.pk} liberado. Factura ARCA detectada: {factura_encontrada['cae']}")
            except Exception as e:
                logger.error(f"Error al re-liberar Hito {hito.pk}: {e}")

    return f"Procesados: {procesados}, Liberados automáticamente: {liberados}"


def _mock_consultar_arca(cuit_emisor, monto_esperado):
    """
    Simulación de consulta al WS de ARCA (AFIP).
    En producción, usaría wsfev1 o similar para buscar comprobantes.
    """
    # Devolvemos un CAE falso para propósitos de prueba el 10% de las veces.
    import random
    if random.random() < 0.1:
        return {"cae": f"CAE-{random.randint(10000000, 99999999)}"}
    return None
