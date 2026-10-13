from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from .models import OPEtapaTracking, OPEtapaLog

# -------------------------------------------------------------------------
# LOG AUDITABLE DE CAMBIOS EN ETAPAS DE TALLERISTAS
# -------------------------------------------------------------------------
@receiver(pre_save, sender=OPEtapaTracking)
def capturar_estado_etapa(sender, instance, **kwargs):
    if instance.pk:
        old = OPEtapaTracking.objects.filter(pk=instance.pk).values("estado").first()
        instance._old_estado = old["estado"] if old else None
    else:
        instance._old_estado = None


@receiver(post_save, sender=OPEtapaTracking)
def registrar_log_etapa(sender, instance, created, **kwargs):
    estado_viejo = getattr(instance, "_old_estado", None)
    estado_nuevo = instance.estado

    if created or estado_viejo != estado_nuevo:
        OPEtapaLog.objects.create(
            etapa_tracking=instance,
            usuario=instance.responsable_interno,
            estado_anterior=estado_viejo or "creada",
            estado_nuevo=estado_nuevo,
            observacion=f"Cambio automático de estado a {instance.get_estado_display()}",
        )
