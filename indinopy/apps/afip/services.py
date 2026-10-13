import logging
from decimal import Decimal
from typing import Dict, Any, Optional
from django.utils import timezone
from apps.base.models import ConfiguracionEmpresa
from apps.eop.models import EOPHitoEscrow, ContratoEOP
from apps.eop.services import UCIService
from .client import AFIPClientFactory
from .facturacion import FacturadorAFIP

logger = logging.getLogger(__name__)


class FacturacionAsistidaService:
    """
    Servicio de Facturación Asistida para Monotributo Productivo (Art. 24.5 y Anexo III Ley e-OP).
    - Prepara el borrador de Factura C ante la recepción conforme del lote productivo.
    - Liquida la micro-retención previsional del 2% con destino al SIPA.
    - Conecta directamente con WSFEv1 para autorizar el CAE y liberar los fondos de Escrow.
    """

    ALICUOTA_RETENCION_SIPA = Decimal("0.02")  # 2%

    @classmethod
    def preparar_borrador_factura_c(cls, hito_id: int) -> Dict[str, Any]:
        """
        Construye el borrador de Factura C asistida para un hito (típicamente el Hito Final / RCF)
        conforme los parámetros del contrato y las partes intervinientes.
        """
        hito = EOPHitoEscrow.objects.select_related("contrato", "contrato__orden_produccion_local").get(id=hito_id)
        contrato = hito.contrato

        # Obtener cotización UCI
        cotizacion_uci = UCIService.obtener_cotizacion_actual()
        if not cotizacion_uci or cotizacion_uci <= 0:
            cotizacion_uci = Decimal("1.00")

        # Calcular monto en UCI y ARS del tramo
        porcentaje = Decimal(str(hito.porcentaje_tramo)) / Decimal("100.00")
        monto_tramo_uci = round(contrato.costo_mod * porcentaje, 2)
        monto_tramo_ars = round(monto_tramo_uci * cotizacion_uci, 2)

        # Micro-retención SIPA 2% (Art. 24.5)
        monto_retencion_sipa_ars = round(monto_tramo_ars * cls.ALICUOTA_RETENCION_SIPA, 2)
        monto_neto_liquidar_ars = monto_tramo_ars - monto_retencion_sipa_ars

        # Obtener emisor (Tallerista) y receptor (Comitente)
        empresa_local = ConfiguracionEmpresa.first_or_create() if hasattr(ConfiguracionEmpresa, "first_or_create") else ConfiguracionEmpresa.get_solo()
        comitente_cuit = empresa_local.cuit or ""
        comitente_razon_social = empresa_local.razon_social or ""

        # Tallerista datos
        tallerista_cuit = ""
        tallerista_nombre = ""
        if contrato.ptf_asignado:
            tallerista_cuit = contrato.ptf_asignado.cuil or contrato.ptf_asignado.cuit or ""
            tallerista_nombre = contrato.ptf_asignado.nombre or ""
        elif contrato.orden_produccion_local:
            etapa = contrato.orden_produccion_local.tracking_etapas.filter(tallerista_asignado__isnull=False).first()
            if etapa and etapa.tallerista_asignado:
                tallerista_cuit = etapa.tallerista_asignado.cuil or etapa.tallerista_asignado.cuit or ""
                tallerista_nombre = etapa.tallerista_asignado.nombre or ""

        numero_op = contrato.numero or str(contrato.uuid_identificador)[:8]
        descripcion_servicio = (
            f"Servicios de Confección y Manufactura Textil s/e-OP {numero_op} "
            f"- Tramo: {hito.nombre}. Ley e-OP Art. 24.5."
        )

        borrador = {
            "hito_id": hito.id,
            "contrato_uuid": str(contrato.uuid_identificador),
            "contrato_numero": contrato.numero or "",
            "tipo_comprobante": "Factura C (Código 011)",
            "cbte_tipo_afip": 11,
            "emisor": {
                "cuit": tallerista_cuit,
                "razon_social": tallerista_nombre,
                "condicion_iva": "Monotributo Productivo",
            },
            "receptor": {
                "cuit": comitente_cuit,
                "razon_social": comitente_razon_social,
                "condicion_iva": getattr(empresa_local, "condicion_iva", "Responsable Inscripto"),
            },
            "concepto": 2,  # Servicios
            "descripcion": descripcion_servicio,
            "monto_total_ars": float(monto_tramo_ars),
            "monto_retencion_sipa_ars": float(monto_retencion_sipa_ars),
            "monto_neto_a_cobrar_ars": float(monto_neto_liquidar_ars),
            "cotizacion_uci": float(cotizacion_uci),
            "monto_tramo_uci": float(monto_tramo_uci),
            "leyenda_legal": "Operación cancelatoria de e-OP. No computable para Factura de Crédito Electrónica MiPyME (Art. 9° Ley e-OP).",
        }

        return borrador

    @classmethod
    def confirmar_y_emitir_factura_asistida(
        cls, hito_id: int, punto_venta: int, ca_existente: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Emite o registra la Factura C asistida:
        - Si se provee ca_existente (cargado por el tallerista desde el Facturador Oficial de ARCA), lo vincula.
        - De lo contrario, solicita el CAE directamente a WSFEv1.
        - Actualiza el hito y ejecuta la liberación del Escrow.
        """
        hito = EOPHitoEscrow.objects.select_related("contrato").get(id=hito_id)
        borrador = cls.preparar_borrador_factura_c(hito_id)

        cae = ca_existente
        fecha_vto_cae = timezone.now().date()
        comprobante_numero = ""

        if not cae:
            # Emisión directa vía WSFEv1
            afip_client = AFIPClientFactory.get_client()
            tipo_cbte = borrador["cbte_tipo_afip"]

            last_voucher = afip_client.ElectronicBilling.getLastVoucher(punto_venta, tipo_cbte)
            next_voucher = last_voucher + 1

            cuit_receptor = str(borrador["receptor"]["cuit"]).replace("-", "").strip()
            hoy_int = int(timezone.now().strftime("%Y%m%d"))

            payload_wsfe = {
                "CantReg": 1,
                "PtoVta": punto_venta,
                "CbteTipo": tipo_cbte,
                "Concepto": borrador["concepto"],
                "DocTipo": 80 if len(cuit_receptor) == 11 else 99,
                "DocNro": int(cuit_receptor) if cuit_receptor.isdigit() else 0,
                "CbteDesde": next_voucher,
                "CbteHasta": next_voucher,
                "CbteFch": hoy_int,
                "FchServDesde": hoy_int,
                "FchServHasta": hoy_int,
                "FchVtoPago": hoy_int,
                "ImpTotal": borrador["monto_total_ars"],
                "ImpTotConc": 0.0,
                "ImpNeto": borrador["monto_total_ars"],
                "ImpOpEx": 0.0,
                "ImpTrib": 0.0,
                "ImpIVA": 0.0,
                "MonId": "PES",
                "MonCotiz": 1.0,
            }

            res = afip_client.ElectronicBilling.createVoucher(payload_wsfe)
            cae = res["CAE"]
            comprobante_numero = f"{punto_venta:04d}-{next_voucher:08d}"

        # Guardar en el hito y registrar metadatos de micro-retención SIPA
        hito.factura_asociada_arca = cae
        ddjj = dict(hito.ddjj_avance_datos or {})
        ddjj["facturacion_asistida"] = {
            "cae": cae,
            "comprobante_numero": comprobante_numero,
            "monto_total_ars": borrador["monto_total_ars"],
            "retencion_sipa_2_porc_ars": borrador["monto_retencion_sipa_ars"],
            "neto_tallerista_ars": borrador["monto_neto_a_cobrar_ars"],
            "fecha_emision": timezone.now().isoformat(),
        }
        hito.ddjj_avance_datos = ddjj
        hito.save(update_fields=["factura_asociada_arca", "ddjj_avance_datos"])

        # Desbloquear / liberar el hito si estaba retenido en RCF
        from apps.eop.services import EOPService
        EOPService.liberar_hito(hito.id)

        logger.info(
            f"Factura Asistida autorizada con CAE {cae} para el Hito {hito.id}. "
            f"Retención SIPA 2%: ${borrador['monto_retencion_sipa_ars']}."
        )

        return {
            "cae": cae,
            "comprobante_numero": comprobante_numero,
            "retencion_sipa_ars": borrador["monto_retencion_sipa_ars"],
            "neto_ars": borrador["monto_neto_a_cobrar_ars"],
            "estado_hito": hito.estado,
        }

    @classmethod
    def constatar_factura_externa(
        cls,
        cuit_emisor: str,
        pto_vta: int,
        cbte_tipo: int,
        cbte_nro: int,
        cbte_fch: str,
        imp_total: float,
        cae: str,
        cuit_receptor: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Constata la validez oficial de un comprobante emitido por terceros ante ARCA
        utilizando el servicio WSCDC (Web Service de Constatación de Comprobantes).
        """
        afip_client = AFIPClientFactory.get_client()
        cuit_emisor_limpio = int(str(cuit_emisor).replace("-", "").strip())
        cuit_rec_limpio = int(str(cuit_receptor).replace("-", "").strip()) if cuit_receptor else 0

        res = afip_client.ComprobanteConstatacion.constatar_comprobante(
            cuit_emisor=cuit_emisor_limpio,
            pto_vta=pto_vta,
            cbte_tipo=cbte_tipo,
            cbte_nro=cbte_nro,
            cbte_fch=cbte_fch,
            imp_total=imp_total,
            cae=cae,
            doc_tipo_receptor=80 if cuit_rec_limpio > 0 else 99,
            doc_nro_receptor=cuit_rec_limpio,
        )

        logger.info(
            f"Constatación WSCDC para comprobante {pto_vta:04d}-{cbte_nro:08d} (Emisor {cuit_emisor_limpio}): "
            f"Resultado {res['resultado']}."
        )
        return res
