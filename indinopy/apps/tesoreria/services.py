from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from apps.tesoreria.models import (
    ComprobanteTesoreria,
    MovimientoCaja,
    Caja,
)
from apps.eop.models import ContratoEOP
from apps.eop.services import EOPService

class TesoreriaService:
    @staticmethod
    @transaction.atomic
    def procesar_repago_marca(comprobante_id):
        comprobante = ComprobanteTesoreria.objects.get(id=comprobante_id)
        if comprobante.tipo == "recibo" and comprobante.estado == "confirmado" and comprobante.escrow_asociado:
            escrow = comprobante.escrow_asociado
            if escrow.estado_escrow == "liquidado_total":
                escrow.estado_escrow = "repago_completado"
                escrow.save(update_fields=["estado_escrow"])
            elif escrow.estado_escrow == "solicitado":
                EOPService.fondear_escrow(escrow.id, comprobante.id)
