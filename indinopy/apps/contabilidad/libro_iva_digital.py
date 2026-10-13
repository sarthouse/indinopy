import logging
from decimal import Decimal
from typing import List, Dict, Any, Tuple, Optional
from django.utils import timezone

logger = logging.getLogger(__name__)


class LibroIVADigitalService:
    """
    Generador de archivos de importación para el Libro de IVA Digital (RG AFIP N° 4597/2019).
    Soporta:
    1. LIBRO_IVA_DIGITAL_COMPRAS_CBTE.txt (Registro de Comprobantes de Compras)
    2. LIBRO_IVA_DIGITAL_COMPRAS_ALICUOTAS.txt (Registro de Alícuotas de IVA)
    3. Incorporación del Crédito Fiscal Presunto del 10% (Art. 23.1 Ley e-OP)
       asociado a contratos e-OP con monotributistas productivos.
    """

    @classmethod
    def generar_linea_comprobante_compra(
        cls,
        fecha_cbte: Any,
        tipo_cbte: int,
        pto_vta: int,
        nro_cbte: int,
        cuit_emisor: str,
        nombre_emisor: str,
        imp_total: Decimal,
        imp_neto: Decimal,
        imp_op_exentas: Decimal = Decimal("0.00"),
        imp_iva: Decimal = Decimal("0.00"),
        imp_tributos: Decimal = Decimal("0.00"),
        codigo_moneda: str = "PES",
        tipo_cambio: Decimal = Decimal("1.000000"),
        cant_alicuotas: int = 1,
        codigo_operacion: str = "0",  # 0: No gravado/General
        credito_fiscal_computable: Optional[Decimal] = None,
    ) -> str:
        """
        Formatea un registro de longitud fija conforme las especificaciones de RG 4597/2019.
        """
        fch_str = fecha_cbte.strftime("%Y%m%d") if hasattr(fecha_cbte, "strftime") else str(fecha_cbte).replace("-", "")[:8]
        tipo_str = f"{int(tipo_cbte):03d}"
        pto_str = f"{int(pto_vta):05d}"
        nro_str = f"{int(nro_cbte):020d}"
        despacho_str = " " * 16
        tipo_doc_emisor = "80"  # CUIT
        cuit_clean = str(cuit_emisor).replace("-", "").strip()[:11].zfill(11)
        denominacion = str(nombre_emisor)[:30].ljust(30)

        # Importes en centavos (sin punto decimal), con signo implícito o 15 dígitos
        def _fmt_imp(val: Decimal, longitud: int = 15) -> str:
            signo = "-" if val < 0 else ""
            centavos = abs(int(round(val * 100)))
            return f"{signo}{centavos:0{longitud}d}"[-longitud:]

        total_fmt = _fmt_imp(imp_total)
        neto_no_gravado = _fmt_imp(Decimal("0.00"))
        exento_fmt = _fmt_imp(imp_op_exentas)
        perc_iva = _fmt_imp(Decimal("0.00"))
        perc_nacionales = _fmt_imp(Decimal("0.00"))
        perc_iibb = _fmt_imp(imp_tributos)
        perc_municipales = _fmt_imp(Decimal("0.00"))
        imp_internos = _fmt_imp(Decimal("0.00"))
        moneda_fmt = (codigo_moneda or "PES")[:3].ljust(3)
        tc_centavos = int(round(tipo_cambio * 1000000))
        tc_fmt = f"{tc_centavos:010d}"
        cant_alic_fmt = f"{cant_alicuotas:01d}"
        cod_operacion_fmt = (codigo_operacion or "0")[:1]
        cf_computable_val = imp_iva if credito_fiscal_computable is None else credito_fiscal_computable
        cf_computable_fmt = _fmt_imp(cf_computable_val)
        otros_tributos = _fmt_imp(Decimal("0.00"))
        cuit_emisor_corredor = "0" * 11
        denominacion_corredor = " " * 30
        iva_comision = _fmt_imp(Decimal("0.00"))

        linea = (
            f"{fch_str}{tipo_str}{pto_str}{nro_str}{despacho_str}{tipo_doc_emisor}"
            f"{cuit_clean}{denominacion}{total_fmt}{neto_no_gravado}{exento_fmt}"
            f"{perc_iva}{perc_nacionales}{perc_iibb}{perc_municipales}{imp_internos}"
            f"{moneda_fmt}{tc_fmt}{cant_alic_fmt}{cod_operacion_fmt}{cf_computable_fmt}"
            f"{otros_tributos}{cuit_emisor_corredor}{denominacion_corredor}{iva_comision}"
        )
        return linea

    @classmethod
    def generar_registro_credito_presunto_eop(cls, contrato_eop, cotizacion_uci: Decimal) -> Tuple[str, str]:
        """
        Genera el registro para Libro IVA Digital del Crédito Fiscal Presunto del 10% (Art. 23.1 Ley e-OP)
        computado sobre el c_MOD ejecutado por monotributistas productivos.
        Retorna (linea_comprobante, linea_alicuota).
        """
        mod_ars = round(Decimal(str(contrato_eop.costo_mod)) * cotizacion_uci, 2)
        credito_presunto_ars = round(mod_ars * Decimal("0.10"), 2)

        taller = contrato_eop.ptf_asignado
        cuit_taller = taller.cuil if taller else "30000000000"
        nombre_taller = taller.nombre if taller else "Taller Monotributo Productivo"
        fecha_emision = contrato_eop.fecha or timezone.now().date()

        # Usamos código de comprobante oficial clase C / Liquidación fiduciaria
        linea_cbte = cls.generar_linea_comprobante_compra(
            fecha_cbte=fecha_emision,
            tipo_cbte=11,  # Factura C
            pto_vta=1,
            nro_cbte=contrato_eop.id,
            cuit_emisor=cuit_taller,
            nombre_emisor=nombre_taller,
            imp_total=mod_ars,
            imp_neto=mod_ars,
            imp_iva=credito_presunto_ars,
            credito_fiscal_computable=credito_presunto_ars,
        )

        # Línea de alícuota correspondiente
        # Formato: Tipo(3) + PtoVta(5) + Nro(20) + CUIT(11) + Neto(15) + CodAlic(4) + Impuesto(15)
        fch_str = fecha_emision.strftime("%Y%m%d")
        pto_str = f"{1:05d}"
        nro_str = f"{contrato_eop.id:020d}"
        cuit_clean = str(cuit_taller).replace("-", "").strip()[:11].zfill(11)

        def _fmt(val):
            return f"{abs(int(round(val * 100))):015d}"

        # Código de alícuota 10% oficial o presunta (0004 = 10.5%, 0008 = régimen especial)
        cod_alicuota = "0004"
        linea_alic = f"{fch_str}011{pto_str}{nro_str}{cuit_clean}{_fmt(mod_ars)}{cod_alicuota}{_fmt(credito_presunto_ars)}"

        return linea_cbte, linea_alic
