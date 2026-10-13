import requests
from celery import shared_task
from django.utils import timezone
from django.conf import settings
from apps.comunicaciones.models import CedulaDestinatario
from apps.contactos.models import Contacto


@shared_task
def procesar_notificaciones_tacitas_async():
    """
    Tarea Celery periódica: opera la notificación tácita por 48h de silencio/falta de acuse
    en el Domicilio Electrónico Sectorial del ERP local.
    """
    from apps.comunicaciones.services import ComunicacionOficialService
    total = ComunicacionOficialService.procesar_notificaciones_tacitas()
    return f"Procesadas {total} comunicaciones notificadas de oficio por vencimiento 48h."


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def despachar_cedula_webhook_async(self, cedula_id):
    """
    Tarea Celery asincrónica de despacho de cédula oficial desde el ERP:
    1. Intenta enviar un Webhook HTTP (Push) directo al endpoint del destinatario o de la MES.
    2. Si falla o no tiene endpoint público, notifica al Nodo MES para que la guarde
       en el buzón NovedadFederada de la red.
    """
    try:
        cedula = CedulaDestinatario.objects.select_related("comunicacion").get(pk=cedula_id)
    except CedulaDestinatario.DoesNotExist:
        return f"Cédula {cedula_id} no encontrada."

    comunicacion = cedula.comunicacion

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
        "cuit_destino": cedula.cuit_destino,
        "modo_recepcion": cedula.modo_recepcion,
        "destinatarios_publicos": destinatarios_publicos,
        "hash_seguridad_payload": comunicacion.hash_seguridad_payload,
        "hashes_adjuntos": comunicacion.hashes_adjuntos or [],
        "firma_emisor_ed25519": comunicacion.firma_emisor_ed25519,
        "fecha_emision": comunicacion.fecha_emision.isoformat() if comunicacion.fecha_emision else None,
        "fecha_limite_tacita": cedula.fecha_limite_tacita.isoformat() if cedula.fecha_limite_tacita else None,
    }

    # Determinamos destino: Si el contacto tiene endpoint, o si se despacha al Nodo MES central
    mes_url = getattr(settings, "NODO_MES_URL", "http://localhost:8000").rstrip("/")
    url_webhook = f"{mes_url}/comunicaciones/api/v1/recibir/"

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
            return f"Cédula {cedula.id} despachada con éxito a la Red (HTTP {resp.status_code})."
        else:
            raise requests.RequestException(f"Status code HTTP {resp.status_code}")
    except requests.RequestException as exc:
        try:
            self.retry(exc=exc)
        except Exception:
            return f"Error despachando cédula {cedula.id}: {str(exc)}"
