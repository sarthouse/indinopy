from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.utils import timezone
from .models import ContratoEscrow
from apps.produccion.models import OrdenProduccion


@receiver(pre_save, sender=ContratoEscrow)
def capturar_estado_anterior_escrow(sender, instance, **kwargs):
    if instance.pk:
        old = ContratoEscrow.objects.filter(pk=instance.pk).values("estado").first()
        instance._old_estado = old["estado"] if old else None
    else:
        instance._old_estado = None


@receiver(post_save, sender=ContratoEscrow)
def notificar_fondeo_op(sender, instance, created, **kwargs):
    """
    Si el Escrow pasa a 'fondeado', notificamos a la OP
    para que inicie formalmente el timelock y el proceso productivo.
    """
    estado_viejo = getattr(instance, "_old_estado", None)
    estado_nuevo = instance.estado

    if estado_viejo != "fondeado" and estado_nuevo == "fondeado":
        # Buscar la OP mediante el eop_uuid
        op = OrdenProduccion.objects.filter(
            uuid_identificador=instance.eop_uuid
        ).first()
        if op:
            op.estado_escrow = "fondeado"
            op.fecha_fondeo_escrow = timezone.now()
            op.save(update_fields=["estado_escrow", "fecha_fondeo_escrow"])


from .models import HitoEscrow, ComprobanteTesoreria


@receiver(pre_save, sender=HitoEscrow)
def verificar_firma_ptf(sender, instance, **kwargs):
    """
    Verifica si el Hito recibió la firma del PTF para liberarlo.
    """
    if instance.pk:
        old = (
            HitoEscrow.objects.filter(pk=instance.pk)
            .values("estado", "firmas_digitales")
            .first()
        )
        instance._old_estado = old["estado"] if old else None

        if instance.estado == "bloqueado" and instance.requiere_auditoria_ptf:
            firmas = instance.firmas_digitales or {}
            if "ptf" in firmas:
                instance.estado = "liberado"
    else:
        instance._old_estado = None


@receiver(post_save, sender=HitoEscrow)
def liberar_pago_taller(sender, instance, created, **kwargs):
    """
    Cuando un Hito pasa a liberado, se autogenera la Orden de Pago al Taller.
    """
    estado_viejo = getattr(instance, "_old_estado", None)

    if (
        estado_viejo != "liberado"
        and instance.estado == "liberado"
        and not instance.comprobante_pago
    ):
        op = OrdenProduccion.objects.filter(
            uuid_identificador=instance.contrato.eop_uuid
        ).first()
        if op:
            # Calcular monto a pagar
            monto_hito = (instance.contrato.monto_total_uci * instance.porcentaje) / 100

            # Crear Orden de Pago (ComprobanteTesoreria) a favor del Tallerista
            op_pago = ComprobanteTesoreria.objects.create(
                numero=f"OPG-HITO-{instance.id}-{op.numero}",
                tipo="orden_pago",
                estado="borrador",
                contacto=op.tallerista_principal,
                observaciones=f"Pago liberado por PTF - {instance.nombre} - OP {op.numero}",
            )
            # Todo: crear el movimiento_caja asociado con monto_hito
            instance.comprobante_pago = op_pago
            instance.save(update_fields=["comprobante_pago"])


@receiver(post_save, sender=ComprobanteTesoreria)
def procesar_repago_marca(sender, instance, created, **kwargs):
    """
    Cuando ingresa un Recibo de Cobranza (Repago de la Marca),
    lo asociamos al Escrow para amortizarlo y cerrar el ciclo financiero.
    """
    if (
        instance.tipo == "recibo"
        and instance.estado == "confirmado"
        and instance.escrow_asociado
    ):
        escrow = instance.escrow_asociado
        # Si el escrow ya fue liquidado (el tallerista cobró todo),
        # este repago cierra la deuda de la Marca con el FDI.
        if escrow.estado == "liquidado":
            escrow.estado = "repago_completado"
            escrow.save(update_fields=["estado"])
        elif escrow.estado == "borrador":
            # Si era borrador y entra plata, se fondea
            escrow.comprobante_fondeo = instance
            escrow.estado = "fondeado"
            escrow.save(update_fields=["estado", "comprobante_fondeo"])
