from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from django.contrib.gis.geos import Point
from .models import RegistroEOP, AlertaColusion

@shared_task
def motor_anti_colusion():
    """
    Worker programado que analiza los RegistroEOP recientes en busca de 
    comportamientos anómalos o simulaciones (Slashing).
    Detecta si dos OPs fueron aprobadas casi al mismo tiempo en lugares muy distantes.
    """
    hace_una_hora = timezone.now() - timedelta(hours=1)
    # Buscar OPs aprobadas en la última hora
    ops_recientes = RegistroEOP.objects.filter(
        fecha_registro__gte=hace_una_hora,
        estado="activa"
    )
    
    # Cruzar cada OP contra las otras para detectar colusión geográfica
    ops_list = list(ops_recientes)
    for i in range(len(ops_list)):
        for j in range(i + 1, len(ops_list)):
            op1 = ops_list[i]
            op2 = ops_list[j]
            
            # Si tienen coordenadas GPS
            if op1.taller.coordenadas_gps and op2.taller.coordenadas_gps:
                p1 = op1.taller.coordenadas_gps
                p2 = op2.taller.coordenadas_gps
                
                # Distancia en metros (aproximación en PostGIS)
                distancia = p1.distance(p2) * 100000  # Aprox grados a metros para simplificar si es WGS84
                diferencia_tiempo = abs((op1.fecha_registro - op2.fecha_registro).total_seconds()) / 3600.0
                
                # Regla de Alerta: Si la distancia es > 50km pero la diferencia de tiempo es < 10 mins (0.16h)
                # significa que el mismo PTF o la misma marca simuló firmas simultáneas en lugares imposibles.
                if distancia > 50000 and diferencia_tiempo < 0.16:
                    AlertaColusion.objects.create(
                        taller_cuit_1=op1.taller.cuit_o_dni,
                        taller_cuit_2=op2.taller.cuit_o_dni,
                        distancia_metros=distancia,
                        diferencia_horas=diferencia_tiempo,
                        estado_investigacion="abierta"
                    )


@shared_task
def procesar_silencio_positivo_timelock_async():
    """
    Worker Celery Beat que se ejecuta periódicamente (ej: cada 1 hora).
    Busca todas las e-OPs en estado 'en_revision' cuyo timelock de 48h haya vencido.
    Si no tienen vetos ni resoluciones negativas de la Comisión, aplica Silencio Positivo
    y gatilla la liberación fiduciaria del Hito Cero del Escrow.
    """
    from apps.federacion.tasks import liberar_hito_escrow_async

    ahora = timezone.now()
    eops_a_destrabar = RegistroEOP.objects.filter(
        estado="en_revision",
        timelock_vencimiento__lte=ahora,
    )

    procesadas = []
    for registro in eops_a_destrabar:
        # Verificar que no tenga vetos vigentes
        tiene_veto = registro.resoluciones.filter(es_veto=True).exists()
        if not tiene_veto:
            registro.estado = "aprobado_silencio"
            registro.save(update_fields=["estado"])

            # Disparar liberación fiduciaria asincrónica
            liberar_hito_escrow_async.delay(str(registro.uuid_identificador))
            procesadas.append(str(registro.uuid_identificador))

    return f"Silencio Positivo ejecutado sobre {len(procesadas)} e-OPs: {procesadas}"
