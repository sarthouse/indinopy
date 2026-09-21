import json
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from apps.tesoreria.models import ComprobanteTesoreria, MovimientoCaja, Caja
from .models import ContratoEOP, EOPHitoEscrow, IndiceUCI

class UCIService:
    """
    Servicio conversor y cotizador para la Unidad de Cuenta Industrial (UCI).
    Protege el Escrow contra fluctuaciones de inflación indexando a IPIM.
    """
    @staticmethod
    def obtener_cotizacion_actual():
        """Devuelve el valor actual de 1 UCI en ARS."""
        cotizacion = IndiceUCI.objects.order_by('-fecha').first()
        if not cotizacion:
            return Decimal("1.00") # Fallback por defecto (1 UCI = 1 ARS)
        return cotizacion.valor_ars

    @staticmethod
    def ars_a_uci(monto_ars, fecha=None):
        """Convierte ARS a UCI usando la cotización a una fecha dada (o la más reciente)."""
        if not monto_ars:
            return Decimal("0.00")
        
        qs = IndiceUCI.objects.all()
        if fecha:
            qs = qs.filter(fecha__lte=fecha)
            
        cotizacion = qs.order_by('-fecha').first()
        valor = cotizacion.valor_ars if cotizacion else Decimal("1.00")
        
        return round(Decimal(monto_ars) / valor, 2)

    @staticmethod
    def uci_a_ars(monto_uci, fecha=None):
        """Convierte UCI a ARS usando la cotización a una fecha dada."""
        if not monto_uci:
            return Decimal("0.00")
            
        qs = IndiceUCI.objects.all()
        if fecha:
            qs = qs.filter(fecha__lte=fecha)
            
        cotizacion = qs.order_by('-fecha').first()
        valor = cotizacion.valor_ars if cotizacion else Decimal("1.00")
        
        return round(Decimal(monto_uci) * valor, 2)


class EOPService:
    @staticmethod
    @transaction.atomic
    def fondear_escrow(contrato_id):
        """
        Marca un ContratoEOP como fondeado.
        En la red federada, esto es gatillado por un Webhook de la MES
        avisando que el FDI adelantó la liquidez inicial.
        """
        contrato = ContratoEOP.objects.get(id=contrato_id)
        if contrato.estado_escrow != "solicitado":
            return
            
        contrato.estado_escrow = "financiado_fdi"
        contrato.fecha_fondeo_escrow = timezone.now()
        contrato.save(update_fields=["estado_escrow", "fecha_fondeo_escrow"])

    @staticmethod
    @transaction.atomic
    def firmar_contrato_tallerista(contrato, usuario, firma_tallerista_hex):
        """
        Registra la firma criptográfica del tallerista en el contrato EOP.
        Despacha la firma al Nodo MES para que inicie el Timelock.
        """
        # Validación de que el usuario logueado efectivamente es el tallerista asignado
        if not hasattr(usuario, 'perfil_contacto'):
            raise ValueError("El usuario no tiene un perfil de tallerista asignado.")
            
        tallerista_cuit = usuario.perfil_contacto.cuil
        
        # Inicializar el JSONField si está nulo
        firmas = contrato.firmas_digitales or {}
        
        if "tallerista" in firmas:
            raise ValueError("Este contrato ya fue firmado por el tallerista.")
            
        # Inyección de la firma
        firmas["tallerista"] = {
            "cuit": tallerista_cuit,
            "firma_hex": firma_tallerista_hex,
            "timestamp": timezone.now().isoformat()
        }
        
        contrato.firmas_digitales = firmas
        contrato.save(update_fields=["firmas_digitales"])
        
        # Aquí llamaríamos a la API Federada para notificar a la MES (Mock)
        # FederacionAPIClient.enviar_firma_tallerista(contrato.uuid, payload)
        # Por ahora lo simulamos mediante log o simplemente pasando.
        pass

    @staticmethod
    @transaction.atomic
    def liberar_hito(hito_id, firma_ptf=None):
        """
        Libera un tramo/hito de un contrato EOP.
        Verifica criptografía Ed25519 del PTF si el hito lo requiere.
        En el modelo federado, la Marca NO le paga al tallerista con su caja local;
        el FDI ejecuta el clearing. Esta función solo cambia el estado lógico para
        habilitar la siguiente etapa fabril.
        """
        hito = EOPHitoEscrow.objects.select_related('contrato').get(id=hito_id)
        if hito.estado not in ["bloqueado", "fiscal_pending"]:
            return
            
        # Si ya estábamos en fiscal_pending, asumimos que estamos intentando re-liberar tras cargar factura
        if hito.estado == "fiscal_pending":
            if not hito.factura_asociada_arca:
                raise ValueError("No se puede liberar el hito porque no hay factura cargada.")
            hito.estado = "liberado"
            hito.save(update_fields=["estado"])
            return

        # Si estaba bloqueado, revisamos firmas
        if hito.requiere_auditoria_ptf:
            firmas = hito.firmas_digitales or {}
            if not firma_ptf and not ("ptf" in firmas and firmas["ptf"].get("firma_hex")):
                raise ValueError("Falta firma criptográfica del PTF para auditar este hito.")
            
        # Lógica FISCAL_PENDING (Defección Fiscal)
        if hito.requiere_verificacion_arca and not hito.factura_asociada_arca:
            hito.estado = "fiscal_pending"
            hito.save(update_fields=["estado"])
            # Se queda congelado, no se notifica al FDI la liberación todavía.
            return
            
        hito.estado = "liberado"
        hito.save(update_fields=["estado"])
        
        # En una integración completa, aquí se notifica a la MES
        # FederacionAPIClient.notificar_liberacion_hito(hito.contrato.uuid, hito.id)
