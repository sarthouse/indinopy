from django.dispatch import receiver
from django.db.models.signals import post_save
from apps.produccion.models import OPParteProduccion, OPEtapaTracking
from apps.eop.models import ContratoEOP
from apps.eop.services import EOPService

# Estas signals actúan como puente asíncrono para que ProduccionService no deba
# importar nada de EOP, garantizando el aislamiento del dominio.

@receiver(post_save, sender=OPParteProduccion)
def notificar_avance_fisico_eop(sender, instance, created, **kwargs):
    """
    Paso 1: El Tallerista declara pares producidos.
    Si este avance hace que la etapa llegue al 100%, la señal debe
    notificar a la MES para que despache al PTF a auditar.
    """
    if created and instance.op:
        contrato = ContratoEOP.objects.filter(orden_produccion_local=instance.op).first()
        if contrato:
            etapa = instance.etapa_tracking
            if etapa:
                # Verificamos si con este parte la etapa llegó al 100%
                # Si llegó al 100%, disparamos la solicitud de auditoría a la MES
                # FederacionAPIClient.solicitar_auditoria_ptf(contrato.uuid, etapa.id)
                pass


@receiver(post_save, sender=OPEtapaTracking)
def notificar_cambio_etapa_eop(sender, instance, **kwargs):
    """
    Paso 2: Cuando el PTF va al taller, firma el avance (llegó al 100%),
    la MES procesa la auditoría, le pide al FDI que transfiera la plata,
    y luego la MES nos avisa a nosotros mediante un webhook.
    Ese webhook pondrá esta etapa como 'finalizada', lo cual gatilla 
    lógicamente la habilitación de la siguiente etapa.
    """
    if instance.estado == 'finalizada' and instance.op:
        contrato = ContratoEOP.objects.filter(orden_produccion_local=instance.op).first()
        if contrato:
            # Aquí la etapa ya está cerrada legalmente y el FDI ya pagó.
            # El ERP local puede avanzar a la siguiente etapa fabril.
            pass
