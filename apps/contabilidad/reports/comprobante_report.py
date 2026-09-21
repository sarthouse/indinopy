import base64
from decimal import Decimal
from typing import Any, Dict
from django.utils import timezone
from apps.base.models import ConfiguracionEmpresa
from apps.base.reports.base import BasePDFReport
from apps.afip.qr import AFIPQRGenerator


class ComprobanteFiscalPDFReport(BasePDFReport):
    """
    Reporte PDF unificado para Facturas, Notas de Débito, Notas de Crédito y Comprobantes X.
    Parametriza el layout fiscal conforme a las normativas de AFIP/ARCA (RG 1415 y RG 4291).
    """

    template_name = "contabilidad/reports/comprobante_fiscal_pdf.html"

    def __init__(self, documento):
        self.documento = documento
        super().__init__()

    def get_filename(self) -> str:
        numero_limpio = (self.documento.numero or f"DOC-{self.documento.id}").replace(" ", "_")
        return f"{self.documento.tipo}_{numero_limpio}.pdf"

    def get_context_data(self) -> Dict[str, Any]:
        doc = self.documento
        empresa = ConfiguracionEmpresa.get_solo()
        contacto = doc.contacto
        tipo_afip = doc.tipo_comprobante_afip

        # Determinación de clasificación y títulos
        es_fiscal = bool(doc.afip_cae and tipo_afip)
        es_nota_credito = "nota_credito" in doc.tipo
        es_nota_debito = "nota_debito" in doc.tipo
        es_comprobante_x = (not es_fiscal) or (tipo_afip and tipo_afip.letra == "X")

        if es_nota_credito:
            titulo_documento = "NOTA DE CRÉDITO"
        elif es_nota_debito:
            titulo_documento = "NOTA DE DÉBITO"
        elif es_comprobante_x:
            titulo_documento = "COMPROBANTE X"
        else:
            titulo_documento = "FACTURA"

        letra = tipo_afip.letra if tipo_afip else "X"
        codigo_afip = tipo_afip.codigo if tipo_afip else "000"
        discrimina_iva = letra in ["A", "M"]

        # Parsear punto de venta y número
        pto_vta_str = "0001"
        nro_cmp_str = "00000001"
        try:
            partes = doc.numero.split("-")
            if len(partes) >= 2:
                pto_vta_str = partes[0].strip()[-4:].zfill(4)
                nro_cmp_str = partes[1].strip()[-8:].zfill(8)
            else:
                nro_cmp_str = str(doc.id).zfill(8)
        except Exception:
            pass

        # Generar QR AFIP oficial si posee CAE
        qr_data_uri = None
        if es_fiscal and doc.afip_cae:
            try:
                cuit_emisor = int(empresa.cuit.replace("-", "").strip() or "0")
                cuit_receptor = int(contacto.cuit.replace("-", "").strip() or "0")
                pto_vta_int = int(pto_vta_str)
                nro_cmp_int = int(nro_cmp_str)
                tipo_cmp_int = int(codigo_afip)
                moneda_cod = doc.moneda.afip_codigo if doc.moneda else "PES"
                cotiz = float(doc.tasa_cambio or 1.0)
                imp_total = float(doc.monto_total)
                fecha_str = doc.fecha_emision.strftime("%Y-%m-%d")

                url_afip = AFIPQRGenerator.construir_url_afip(
                    fecha=fecha_str,
                    cuit_emisor=cuit_emisor,
                    punto_venta=pto_vta_int,
                    tipo_comprobante=tipo_cmp_int,
                    numero_comprobante=nro_cmp_int,
                    importe_total=imp_total,
                    moneda=moneda_cod,
                    cotizacion=cotiz,
                    tipo_doc_receptor=80 if cuit_receptor > 0 else 99,
                    nro_doc_receptor=cuit_receptor,
                    tipo_codigo_autorizacion="E",
                    codigo_autorizacion=int(doc.afip_cae),
                )
                qr_data_uri = AFIPQRGenerator.generar_qr_data_uri(url_afip)
            except Exception:
                qr_data_uri = None

        # Desglose de alícuotas de IVA
        alicuotas_iva = []
        if discrimina_iva:
            iva_acum = {}
            for linea in doc.lineas.all():
                if linea.impuesto and linea.impuesto.alicuota > 0:
                    alic = linea.impuesto.alicuota
                    if alic not in iva_acum:
                        iva_acum[alic] = {"base": Decimal("0.00"), "importe": Decimal("0.00")}
                    iva_acum[alic]["base"] += linea.subtotal
                    iva_acum[alic]["importe"] += (linea.subtotal * alic) / Decimal("100.00")
            alicuotas_iva = [
                {"alicuota": k, "base": v["base"], "importe": v["importe"]}
                for k, v in sorted(iva_acum.items())
            ]

        # Logo de la empresa en base64
        logo_data_uri = None
        if empresa.logo:
            try:
                with open(empresa.logo.path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("utf-8")
                    logo_data_uri = f"data:image/png;base64,{b64}"
            except Exception:
                pass

        return {
            "documento": doc,
            "empresa": empresa,
            "contacto": contacto,
            "tipo_afip": tipo_afip,
            "titulo_documento": titulo_documento,
            "letra": letra,
            "codigo_afip": codigo_afip,
            "es_fiscal": es_fiscal,
            "es_nota_credito": es_nota_credito,
            "es_nota_debito": es_nota_debito,
            "es_comprobante_x": es_comprobante_x,
            "discrimina_iva": discrimina_iva,
            "es_mipyme_fce": bool(tipo_afip and tipo_afip.es_mipyme_fce),
            "pto_vta_str": pto_vta_str,
            "nro_cmp_str": nro_cmp_str,
            "qr_data_uri": qr_data_uri,
            "logo_data_uri": logo_data_uri,
            "alicuotas_iva": alicuotas_iva,
            "tributos": doc.tributos.all() if hasattr(doc, "tributos") else [],
            "lineas": doc.lineas.all(),
            "es_consumidor_final": getattr(contacto, "condicion_iva", "") == "consumidor_final",
            "ahora": timezone.now(),
        }
