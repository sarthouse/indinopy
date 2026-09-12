import requests
from celery import shared_task
from django.conf import settings
from apps.mes.models import RegistroEOP
from apps.federacion.models import NodoFederado
from apps.tesoreria.services import EscrowService

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
        # Aquí Celery podría reintentar (retry) automáticamente
        raise Exception(f"Fallo de conexión con Nodo Tallerista: {str(e)}")


@shared_task
def liberar_hito_escrow_async(uuid_str):
    """
    Tarea Celery asincrónica que ejecuta el movimiento pesado de tesorería
    (liberar fondos del Smart Contract / Fideicomiso) sin bloquear el request web.
    """
    try:
        registro = RegistroEOP.objects.get(uuid_identificador=uuid_str)
        # La MES ordena la liberación del dinero a los trabajadores
        EscrowService.liberar_hito(str(registro.uuid_identificador))
        
        return f"Escrow liberado exitosamente para e-OP {uuid_str}."
        
    except RegistroEOP.DoesNotExist:
        return f"Error: No se encontró RegistroEOP {uuid_str}."
    except Exception as e:
        return f"Error liberando Escrow: {str(e)}"
