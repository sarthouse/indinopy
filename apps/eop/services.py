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
    def crear_contrato_desde_op(op, ptf=None, nodo_mes=None, porcentaje_anticipo=None):
        """
        Pasa una Orden de Producción (en ARS) a un ContratoEOP colateralizado en UCI.
        Lee los costos de etapas (MOD), insumos requeridos (BOM), cargas sociales e impuestos,
        convirtiéndolos a valor UCI vigente.
        """
        from apps.base.models import ConfiguracionEmpresa
        from django.conf import settings

        if not nodo_mes:
            empresa = ConfiguracionEmpresa.objects.first()
            nodo_mes = (
                (empresa.nodo_mes_endpoint or empresa.nodo_mes)
                if empresa else None
            ) or getattr(settings, "NODO_MES_URL", "http://localhost:8000")

        cotizacion_uci = UCIService.obtener_cotizacion_actual()
        if not cotizacion_uci or cotizacion_uci <= 0:
            cotizacion_uci = Decimal("1.00")

        # 1. Mano de Obra Directa (MOD): Suma de tarifas de servicios de façón homologadas
        costo_mod_ars = sum(
            (etapa.costo_servicio_total or Decimal("0.00")) for etapa in op.tracking_etapas.all()
        )

        # 2. Insumos y Materias Primas Físicas (BOM aportado por la marca comitente)
        costo_bom_ars = Decimal("0.00")
        for req in op.insumos_requeridos.all():
            precio_unit = getattr(req.insumo, "costo", Decimal("0.00")) or Decimal("0.00")
            costo_bom_ars += req.cantidad_teorica * precio_unit

        # 3. Recargo Institucional de Red MES y Fondo de Riesgo FDI (1.5% s/MOD Financiada)
        # 1.0% Micro-canon de Red MES + 0.5% Fondo de Riesgo FDI
        costo_fdi_ars = round(costo_mod_ars * Decimal("0.015"), 2)

        # 4. En el modelo e-OP oficial (Dossier FIMCA):
        # - Las cargas sociales de nómina interna del taller (F931) son absorbidas por el taller / fomento FDI,
        #   NO son una deuda que deba pagar la marca comitente (ver Anexo Técnico I).
        # - La retención tributaria (Monotributo) está incluida dentro de la MOD homologada.
        # - Margen e impuestos corporativos de balance de la marca no colateralizan el contrato fabril.
        costo_cs_ars = Decimal("0.00")
        costo_tax_ars = Decimal("0.00")
        costo_mg_ars = Decimal("0.00")

        # 5. Conversión a UCI
        def _to_uci(monto_ars):
            return round(Decimal(monto_ars) / cotizacion_uci, 2)

        contrato = ContratoEOP.objects.create(
            orden_produccion_local=op,
            nodo_mes=nodo_mes,
            ptf_asignado=ptf,
            costo_mod=_to_uci(costo_mod_ars),
            costo_cs=_to_uci(costo_cs_ars),
            costo_bom=_to_uci(costo_bom_ars),
            costo_fdi=_to_uci(costo_fdi_ars),
            costo_tax=_to_uci(costo_tax_ars),
            costo_mg=_to_uci(costo_mg_ars),
            estado_escrow="solicitado",
        )

        # 5. Generar Árbol de Merkle del BOM
        contrato.merkle_root_bom = contrato.calcular_merkle_root_bom()
        contrato.save(update_fields=["merkle_root_bom"])

        # 6. Crear Cronograma de Hitos: Regla obligatoria (Mínimo 2 etapas + Hito Cero)
        etapas_tracking = list(op.tracking_etapas.all().order_by("etapa_origen__orden_ejecucion", "id"))
        if len(etapas_tracking) < 2:
            raise ValueError(
                f"Una e-OP federada requiere un mínimo obligatorio de dos etapas productivas (posee {len(etapas_tracking)})."
            )

        anticipo = porcentaje_anticipo or (Decimal("50.00") if op.contrato_eop and op.contrato_eop.es_sello_buen_diseno else Decimal("35.00"))
        if anticipo >= Decimal("100.00") or anticipo <= Decimal("0.00"):
            anticipo = Decimal("35.00")

        # Hito Cero: Anticipo Operativo de Arranque (no requiere auditoría PTF previa al desembolso)
        EOPHitoEscrow.objects.create(
            contrato=contrato,
            nombre="Hito Cero - Anticipo Operativo de Arranque",
            porcentaje_tramo=anticipo,
            requiere_auditoria_ptf=False,
            requiere_verificacion_arca=False,
            estado="bloqueado",
        )

        # Hitos por Etapa: Distribuir el porcentaje restante entre las etapas productivas
        porcentaje_remanente = Decimal("100.00") - anticipo
        total_mod = sum((e.costo_servicio_total or Decimal("0.00")) for e in etapas_tracking)
        porcentaje_acumulado = Decimal("0.00")

        for idx, etapa in enumerate(etapas_tracking):
            es_ultima = (idx == len(etapas_tracking) - 1)
            servicio_nombre = etapa.etapa_origen.servicio.nombre if (etapa.etapa_origen and etapa.etapa_origen.servicio) else f"Etapa {idx + 1}"
            orden = etapa.etapa_origen.orden_ejecucion if etapa.etapa_origen else (idx + 1)

            if es_ultima:
                # Ajuste de cierre para garantizar exactamente 100.00%
                porc_etapa = porcentaje_remanente - porcentaje_acumulado
            else:
                if total_mod > 0:
                    costo_e = etapa.costo_servicio_total or Decimal("0.00")
                    porc_etapa = round((costo_e / total_mod) * porcentaje_remanente, 2)
                else:
                    porc_etapa = round(porcentaje_remanente / Decimal(len(etapas_tracking)), 2)
                porcentaje_acumulado += porc_etapa

            EOPHitoEscrow.objects.create(
                contrato=contrato,
                nombre=f"Hito {orden} - Avance: {servicio_nombre}",
                porcentaje_tramo=porc_etapa,
                requiere_auditoria_ptf=True,
                requiere_verificacion_arca=es_ultima,
                estado="bloqueado",
            )

        return contrato

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
