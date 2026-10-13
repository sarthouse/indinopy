import requests
from celery import shared_task
from django.conf import settings
from federacion.models import NodoFederado

@shared_task
def notificar_tallerista_nueva_eop(uuid_str, tallerista_cuit, payload_original):
    """
    Tarea Celery asincrónica que retransmite la e-OP hacia el servidor del Tallerista
    para que se genere su OP Espejo.
    """
    try:
        nodo_taller = NodoFederado.objects.get(cuit=tallerista_cuit)
        url_webhook = f"{nodo_taller.url_base.rstrip('/')}/api/v1/eop/espejo/"
        
        respuesta = requests.post(
            url_webhook, 
            json=payload_original, 
            timeout=10
        )
        
        if respuesta.status_code == 201:
            return f"Nodo {tallerista_cuit} notificado con éxito."
        else:
            return f"Error notificando Nodo {tallerista_cuit}: {respuesta.status_code}"
            
    except NodoFederado.DoesNotExist:
        return f"El tallerista {tallerista_cuit} no tiene un Nodo Federado registrado."
    except requests.RequestException as e:
        # TODO: Implementar Fallback a NovedadFederada para el Pull
        raise Exception(f"Fallo de conexión con Nodo Tallerista: {str(e)}")


@shared_task
def liberar_hito_escrow_async(uuid_str):
    """
    Tarea Celery asincrónica que ejecuta la liberación fiduciaria del tramo de Escrow
    en la MES sin bloquear el request web.
    """
    try:
        from fdi.models import RegistroEOP
        from fdi.services import PTFService

        registro = RegistroEOP.objects.get(uuid_identificador=uuid_str)
        PTFService._liberar_escrow_por_eop(registro)
        return f"Escrow liberado exitosamente en MES para e-OP {uuid_str}."
    except Exception as e:
        return f"Error liberando Escrow: {str(e)}"






