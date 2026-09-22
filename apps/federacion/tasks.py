import requests
from celery import shared_task
from django.conf import settings
from apps.federacion.models import NodoFederado

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
    Tarea Celery asincrónica que ejecuta el movimiento pesado de tesorería
    (liberar fondos del Smart Contract / Fideicomiso) sin bloquear el request web.
    """
    try:
        from apps.mes.models import RegistroEOP
        from apps.eop.models import ContratoEOP
        from apps.eop.services import EOPService

        registro = RegistroEOP.objects.get(uuid_identificador=uuid_str)
        # La MES ordena la liberación del dinero a los trabajadores (buscamos el Hito Cero)
        # Por simplificación asumimos que el hito 0 es el primero o lo buscamos vía ContratoEOP
        contrato = ContratoEOP.objects.get(uuid_identificador=uuid_str)
        hito_cero = contrato.hitos.order_by('id').first()
        if hito_cero:
            EOPService.liberar_hito(hito_cero.id)
        
        return f"Escrow liberado exitosamente para e-OP {uuid_str}."
        
    except (ImportError, RuntimeError) as e:
        return f"Módulos de gobernanza no disponibles en este nodo: {str(e)}"
    except Exception as e:
        return f"Error liberando Escrow: {str(e)}"


@shared_task
def procesar_notificaciones_tacitas_async():
    """
    Tarea Celery periódica: opera la notificación tácita por 48h de silencio/falta de acuse
    en el Domicilio Electrónico Sectorial.
    """
    from apps.federacion.services import ComunicacionOficialService
    total = ComunicacionOficialService.procesar_notificaciones_tacitas()
    return f"Procesadas {total} comunicaciones notificadas de oficio por vencimiento 48h."


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def despachar_cedula_webhook_async(self, cedula_id):
    """
    Tarea Celery asincrónica de despacho de cédula oficial:
    1. Intenta enviar un Webhook HTTP (Push) al nodo destino.
    2. Si falla por caída de red o nodo offline, reintenta hasta 3 veces (backoff).
    3. Si se agotan los reintentos o el nodo no tiene url_base pública, deposita la cédula
       como NovedadFederada (Pull) en el buzón federado para sincronización cuando el nodo despierte.
    """
    import json
    from django.utils import timezone
    from apps.federacion.models import CedulaDestinatario, NovedadFederada

    try:
        cedula = CedulaDestinatario.objects.select_related(
            "comunicacion", "comunicacion__nodo_emisor", "nodo_destino"
        ).get(pk=cedula_id)
    except CedulaDestinatario.DoesNotExist:
        return f"Cédula {cedula_id} no encontrada."

    comunicacion = cedula.comunicacion
    nodo_dest = cedula.nodo_destino

    # Destinatarios públicos para preservar confidencialidad de CCO
    destinatarios_publicos = [
        {"cuit": d.cuit_destino, "modo": d.modo_recepcion}
        for d in comunicacion.destinatarios.all()
        if d.modo_recepcion in ["principal", "copia_publica"]
    ]

    payload_transporte = {
        "tipo_evento": "cedula_notificacion_oficial",
        "cedula_id": cedula.id,
        "uuid_identificador": str(comunicacion.uuid_identificador),
        "numero_oficial": comunicacion.numero_oficial,
        "tipo": comunicacion.tipo,
        "asunto": comunicacion.asunto,
        "cuerpo_contenido": comunicacion.cuerpo_contenido,
        "es_cifrado": comunicacion.es_cifrado,
        "cuit_emisor": comunicacion.cuit_emisor,
        "nodo_emisor": comunicacion.nodo_emisor.nombre,
        "cuit_destino": cedula.cuit_destino,
        "modo_recepcion": cedula.modo_recepcion,
        "destinatarios_publicos": destinatarios_publicos,
        "hash_seguridad_payload": comunicacion.hash_seguridad_payload,
        "hashes_adjuntos": comunicacion.hashes_adjuntos or [],
        "firma_emisor_ed25519": comunicacion.firma_emisor_ed25519,
        "fecha_emision": comunicacion.fecha_emision.isoformat() if comunicacion.fecha_emision else None,
        "fecha_limite_tacita": cedula.fecha_limite_tacita.isoformat() if cedula.fecha_limite_tacita else None,
    }

    url_base = (nodo_dest.url_base or "").strip().rstrip("/")
    if url_base and not url_base.startswith("http://localhost"):
        url_webhook = f"{url_base}/api/v1/comunicaciones/recibir/"
        try:
            resp = requests.post(
                url_webhook,
                json=payload_transporte,
                headers={"X-Node-CUIT": comunicacion.cuit_emisor, "Content-Type": "application/json"},
                timeout=10,
            )
            if resp.status_code in [200, 201]:
                cedula.estado_notificacion = "entregada"
                if not cedula.fecha_puesta_disposicion:
                    cedula.fecha_puesta_disposicion = timezone.now()
                cedula.save(update_fields=["estado_notificacion", "fecha_puesta_disposicion"])
                return f"Cédula {cedula.id} entregada vía Webhook a {nodo_dest.nombre}."
            else:
                raise requests.RequestException(f"Status code HTTP {resp.status_code}")
        except requests.RequestException as exc:
            # Reintentar con backoff exponencial antes del fallback
            try:
                self.retry(exc=exc)
            except Exception:
                pass  # Agotó reintentos, procede al fallback abajo

    # FALLBACK A NOVEDAD FEDERADA (PULL / STORE-AND-FORWARD)
    novedad, _created = NovedadFederada.objects.get_or_create(
        nodo_destino=nodo_dest,
        tipo_evento="cedula_notificacion_oficial",
        defaults={"payload": payload_transporte, "leido": False},
    )
    if not _created:
        novedad.payload = payload_transporte
        novedad.leido = False
        novedad.save(update_fields=["payload", "leido"])

    cedula.estado_notificacion = "entregada"
    if not cedula.fecha_puesta_disposicion:
        cedula.fecha_puesta_disposicion = timezone.now()
    cedula.save(update_fields=["estado_notificacion", "fecha_puesta_disposicion"])

    return f"Cédula {cedula.id} encolada en buzón NovedadFederada para {nodo_dest.nombre} (Fallback Pull)."


