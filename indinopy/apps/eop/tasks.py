import logging
from decimal import Decimal
from celery import shared_task
from django.utils import timezone
from apps.eop.models import EOPHitoEscrow, ContratoEOP, IncidenciaLogisticaJIT
from apps.eop.services import EOPService, RCFService, LogisticaJITService
from apps.afip.services import FacturacionAsistidaService

logger = logging.getLogger(__name__)


@shared_task
def procesar_timelocks_rcf():
    """
    Tarea periódica (ej. cada hora):
    1. Audita los hitos retenidos en 'retencion_cierre_fiscal' sin factura ARCA.
    2. Si vencieron los 21 días (10 hábiles + 5 de gracia corridos), devenga intereses BADLAR (Art. 12° inc. 3).
    3. Si el tallerista cargó o emitió un CAE, intenta constatarlo y liberar el hito.
    """
    hitos_rcf = EOPHitoEscrow.objects.filter(estado="retencion_cierre_fiscal")
    total = hitos_rcf.count()
    intereses_total = Decimal("0.00")
    liberados = 0

    for hito in hitos_rcf:
        # A. Si ya tiene CAE cargado pero sigue retenido, intentamos liberar
        if hito.factura_asociada_arca:
            try:
                EOPService.liberar_hito(hito.id)
                liberados += 1
                logger.info(f"Hito {hito.id} liberado exitosamente tras constatar CAE {hito.factura_asociada_arca}.")
                continue
            except Exception as exc:
                logger.warning(f"No se pudo liberar hito {hito.id} con CAE: {exc}")

        # B. Auditar timelock y devengar intereses BADLAR si superó la ventana de gracia
        try:
            interes = RCFService.auditar_timelock_rcf(hito.id)
            if interes > Decimal("0.00"):
                intereses_total += interes
                logger.info(f"Devengado ${interes} de interés BADLAR en hito {hito.id} por mora fiscal.")
        except Exception as exc:
            logger.error(f"Error auditando timelock RCF en hito {hito.id}: {exc}")

    return f"Hitos RCF evaluados: {total}. Liberados: {liberados}. Intereses BADLAR devengados: ${intereses_total}"


@shared_task
def procesar_incidencias_jit_y_standby():
    """
    Tarea periódica (ej. diaria a las 06:00):
    Monitorea los contratos con Logística Justo a Tiempo (Art. 5° bis Ley e-OP).
    - Detecta demoras activas en la provisión de insumos por la marca.
    - Actualiza el devengamiento de standby fabril (0.5 SMVM diario a partir del 6° día).
    - Alerta si se alcanzaron los 15 días continuos de mora (habilitando resolución de pleno derecho).
    """
    hoy = timezone.now().date()
    incidencias_abiertas = IncidenciaLogisticaJIT.objects.filter(
        fecha_entrega_real__isnull=True,
        resolucion_ejercida_por_taller=False,
    ).select_related("contrato")

    total = incidencias_abiertas.count()
    actualizadas = 0

    for inc in incidencias_abiertas:
        try:
            LogisticaJITService.registrar_demora_abastecimiento(
                contrato=inc.contrato,
                etapa_nombre=inc.etapa_afectada,
                fecha_esperada=inc.fecha_entrega_esperada,
                fecha_real=hoy,
            )
            actualizadas += 1
        except Exception as exc:
            logger.error(f"Error procesando incidencia JIT {inc.id}: {exc}")

    return f"Incidencias JIT abiertas: {total}. Actualizadas hoy: {actualizadas}."


@shared_task
def constatar_facturas_arca_pendientes():
    """
    Alias / job retrocompatible para constatar comprobantes ARCA en hitos retenidos.
    """
    return procesar_timelocks_rcf()
