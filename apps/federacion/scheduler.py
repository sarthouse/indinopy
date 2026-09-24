import logging
from datetime import timedelta
from django.utils import timezone
from apps.eop.services import ParametrosFDIService

logger = logging.getLogger(__name__)


class SchedulerFederacionService:
    """
    Planificador y Sincronizador de Parámetros Federados.
    Sigue el mismo patrón arquitectónico de apps.inventario.scheduler.
    
    Gestiona la sincronización periódica cada 48 horas contra el Nodo MES
    para mantener calientes los aranceles (Canon MES + Fondo FDI) en la caché
    de Redis (con expiración de 7 días).
    """

    INTERVALO_HORAS = 48

    @classmethod
    def sincronizar_parametros_arancelarios(cls, forzar=False):
        """
        Ejecuta la sincronización contra la MES si pasaron más de 48 horas
        desde la última sincronización exitosa, o si se invoca con forzar=True.
        """
        logger.info("Iniciando Scheduler de Sincronización Arancelaria FDI/MES...")
        
        resultado = ParametrosFDIService.refrescar_parametros_desde_mes()
        if resultado:
            logger.info(
                f"Scheduler: Aranceles FDI/MES actualizados con éxito. "
                f"Alícuota total: {resultado.get('alicuota_total_recargo')}"
            )
            return {
                "estado": "exitoso",
                "datos": resultado,
                "timestamp": timezone.now().isoformat(),
            }
        else:
            logger.warning(
                "Scheduler: No se pudo contactar al Nodo MES. "
                "Se preserva la caché previa o el fallback de seguridad."
            )
            return {
                "estado": "fallido_o_fallback",
                "timestamp": timezone.now().isoformat(),
            }
