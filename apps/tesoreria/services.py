from django.db import transaction
from django.utils import timezone
from apps.tesoreria.models import ContratoEscrow, HitoEscrow, ComprobanteTesoreria, MovimientoCaja, Caja
from apps.produccion.models import OrdenProduccion

class EscrowService:
    @staticmethod
    @transaction.atomic
    def fondear_escrow(escrow_id, comprobante_fondeo_id):
        escrow = ContratoEscrow.objects.get(id=escrow_id)
        if escrow.estado != "borrador":
            return
            
        comprobante_fondeo = ComprobanteTesoreria.objects.get(id=comprobante_fondeo_id)
        escrow.comprobante_fondeo = comprobante_fondeo
        escrow.estado = "fondeado"
        escrow.save(update_fields=["estado", "comprobante_fondeo"])
        
        # Notificar a la OP
        op = OrdenProduccion.objects.filter(uuid_identificador=escrow.eop_uuid).first()
        if op:
            op.estado_escrow = "fondeado"
            op.fecha_fondeo_escrow = timezone.now()
            op.save(update_fields=["estado_escrow", "fecha_fondeo_escrow"])

    @staticmethod
    @transaction.atomic
    def liberar_hito(hito_id, firma_ptf=None):
        hito = HitoEscrow.objects.select_related('contrato').get(id=hito_id)
        if hito.estado != "bloqueado":
            return
            
        if hito.requiere_auditoria_ptf:
            firmas = hito.firmas_digitales or {}
            if not firma_ptf and not ("ptf" in firmas and firmas["ptf"].get("firma_hex")):
                raise ValueError("Falta firma criptográfica del PTF")
            
        hito.estado = "liberado"
        hito.save(update_fields=["estado"])
        
        op = OrdenProduccion.objects.filter(uuid_identificador=hito.contrato.eop_uuid).first()
        if op:
            monto_hito = (hito.contrato.monto_total_uci * hito.porcentaje) / 100

            op_pago = ComprobanteTesoreria.objects.create(
                numero=f"OPG-HITO-{hito.id}-{op.numero}",
                tipo="orden_pago",
                estado="borrador",
                contacto=op.tallerista_principal,
                observaciones=f"Pago liberado por PTF - {hito.nombre} - OP {op.numero}",
            )
            
            caja_defecto = Caja.objects.filter(activa=True).order_by('tipo').first()
            if caja_defecto:
                MovimientoCaja.objects.create(
                    comprobante=op_pago,
                    caja=caja_defecto,
                    tipo_valor="transferencia",
                    monto_egreso=monto_hito,
                    estado="borrador"
                )

            hito.comprobante_pago = op_pago
            hito.save(update_fields=["comprobante_pago"])

class TesoreriaService:
    @staticmethod
    @transaction.atomic
    def procesar_repago_marca(comprobante_id):
        comprobante = ComprobanteTesoreria.objects.get(id=comprobante_id)
        if comprobante.tipo == "recibo" and comprobante.estado == "confirmado" and comprobante.escrow_asociado:
            escrow = comprobante.escrow_asociado
            if escrow.estado == "liquidado":
                escrow.estado = "repago_completado"
                escrow.save(update_fields=["estado"])
            elif escrow.estado == "borrador":
                EscrowService.fondear_escrow(escrow.id, comprobante.id)
