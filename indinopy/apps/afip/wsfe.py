import logging
import xml.etree.ElementTree as ET
from typing import Dict, Any, Optional
import requests

logger = logging.getLogger(__name__)


class WSFEClient:
    """
    Cliente SOAP directo para el Web Service de Facturación Electrónica (WSFEv1) de AFIP/ARCA.
    Interactúa con los endpoints oficiales de AFIP sin intermediarios de terceros.
    """

    URL_HOMO = "https://wswhomo.afip.gov.ar/wsfev1/service.asmx"
    URL_PROD = "https://servicios1.afip.gov.ar/wsfev1/service.asmx"
    SOAP_NS = "http://ar.gov.afip.dif.FEV1/"

    def __init__(self, token: str, sign: str, cuit: int, production: bool = False):
        self.token = token
        self.sign = sign
        self.cuit = cuit
        self.production = production
        self.endpoint = self.URL_PROD if production else self.URL_HOMO

    def _ejecutar_soap(self, action: str, body_xml: str) -> ET.Element:
        """
        Ejecuta una petición SOAP a WSFEv1.
        """
        envelope = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
            f'xmlns:fe="{self.SOAP_NS}">\n'
            "  <soapenv:Header/>\n"
            "  <soapenv:Body>\n"
            f"    {body_xml}\n"
            "  </soapenv:Body>\n"
            "</soapenv:Envelope>"
        )

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": f"{self.SOAP_NS}{action}",
        }

        resp = requests.post(self.endpoint, data=envelope.encode("utf-8"), headers=headers, timeout=20)
        if resp.status_code != 200:
            raise ValueError(f"Error HTTP en llamada a WSFE {action} ({resp.status_code}): {resp.text}")

        root = ET.fromstring(resp.text)
        return root

    def get_last_voucher(self, punto_venta: int, tipo_comprobante: int) -> int:
        """
        Consulta el último número de comprobante autorizado (FECompUltimoAutorizado).
        """
        body_xml = (
            "<fe:FECompUltimoAutorizado>\n"
            "  <fe:Auth>\n"
            f"    <fe:Token>{self.token}</fe:Token>\n"
            f"    <fe:Sign>{self.sign}</fe:Sign>\n"
            f"    <fe:Cuit>{self.cuit}</fe:Cuit>\n"
            "  </fe:Auth>\n"
            f"  <fe:PtoVta>{punto_venta}</fe:PtoVta>\n"
            f"  <fe:CbteTipo>{tipo_comprobante}</fe:CbteTipo>\n"
            "</fe:FECompUltimoAutorizado>"
        )

        root = self._ejecutar_soap("FECompUltimoAutorizado", body_xml)
        
        # Buscar CbteNro
        cbte_nro_elem = root.find(".//{http://ar.gov.afip.dif.FEV1/}CbteNro")
        if cbte_nro_elem is not None and cbte_nro_elem.text:
            return int(cbte_nro_elem.text)

        # Si hay errores
        err_msg = self._extraer_errores(root)
        raise ValueError(f"Error consultando último comprobante en AFIP: {err_msg}")

    def create_voucher(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Solicita la autorización de un comprobante (FECAESolicitar).
        Retorna diccionario con CAE y CAEFchVto.
        """
        req_xml = self._construir_fecae_solicitar_xml(data)
        root = self._ejecutar_soap("FECAESolicitar", req_xml)

        # Validar errores a nivel cabecera
        errores = self._extraer_errores(root)
        if errores:
            raise ValueError(f"Rechazo de AFIP en FECAESolicitar: {errores}")

        # Extraer resultado del detalle
        cae_elem = root.find(".//{http://ar.gov.afip.dif.FEV1/}CAE")
        cae_fch_vto_elem = root.find(".//{http://ar.gov.afip.dif.FEV1/}CAEFchVto")
        resultado_elem = root.find(".//{http://ar.gov.afip.dif.FEV1/}Resultado")

        resultado = resultado_elem.text if resultado_elem is not None else ""
        if resultado != "A":
            obs_msg = self._extraer_observaciones(root)
            raise ValueError(f"Comprobante no autorizado por AFIP (Resultado: {resultado}). Observaciones: {obs_msg}")

        if cae_elem is None or not cae_elem.text:
            raise ValueError("AFIP aprobó la solicitud pero no retornó el CAE.")

        return {
            "CAE": cae_elem.text,
            "CAEFchVto": cae_fch_vto_elem.text if cae_fch_vto_elem is not None else "",
        }

    def _extraer_errores(self, root: ET.Element) -> str:
        errores = []
        for err in root.findall(".//{http://ar.gov.afip.dif.FEV1/}Err"):
            codigo = err.findtext("{http://ar.gov.afip.dif.FEV1/}Code", "")
            msg = err.findtext("{http://ar.gov.afip.dif.FEV1/}Msg", "")
            errores.append(f"[{codigo}] {msg}")
        return " | ".join(errores)

    def _extraer_observaciones(self, root: ET.Element) -> str:
        obs_list = []
        for obs in root.findall(".//{http://ar.gov.afip.dif.FEV1/}Obs"):
            codigo = obs.findtext("{http://ar.gov.afip.dif.FEV1/}Code", "")
            msg = obs.findtext("{http://ar.gov.afip.dif.FEV1/}Msg", "")
            obs_list.append(f"[{codigo}] {msg}")
        return " | ".join(obs_list)

    def _construir_fecae_solicitar_xml(self, data: Dict[str, Any]) -> str:
        pto_vta = data["PtoVta"]
        cbte_tipo = data["CbteTipo"]
        concepto = data.get("Concepto", 1)  # 1: Productos, 2: Servicios, 3: Prod y Serv

        xml_parts = [
            "<fe:FECAESolicitar>",
            "  <fe:Auth>",
            f"    <fe:Token>{self.token}</fe:Token>",
            f"    <fe:Sign>{self.sign}</fe:Sign>",
            f"    <fe:Cuit>{self.cuit}</fe:Cuit>",
            "  </fe:Auth>",
            "  <fe:FeCAEReq>",
            "    <fe:FeCabReq>",
            f"      <fe:CantReg>{data.get('CantReg', 1)}</fe:CantReg>",
            f"      <fe:PtoVta>{pto_vta}</fe:PtoVta>",
            f"      <fe:CbteTipo>{cbte_tipo}</fe:CbteTipo>",
            "    </fe:FeCabReq>",
            "    <fe:FeDetReq>",
            "      <fe:FECAEDetRequest>",
            f"        <fe:Concepto>{concepto}</fe:Concepto>",
            f"        <fe:DocTipo>{data.get('DocTipo', 99)}</fe:DocTipo>",
            f"        <fe:DocNro>{data.get('DocNro', 0)}</fe:DocNro>",
            f"        <fe:CbteDesde>{data['CbteDesde']}</fe:CbteDesde>",
            f"        <fe:CbteHasta>{data['CbteHasta']}</fe:CbteHasta>",
            f"        <fe:CbteFch>{data['CbteFch']}</fe:CbteFch>",
            f"        <fe:ImpTotal>{data['ImpTotal']:.2f}</fe:ImpTotal>",
            f"        <fe:ImpTotConc>{data.get('ImpTotConc', 0.0):.2f}</fe:ImpTotConc>",
            f"        <fe:ImpNeto>{data.get('ImpNeto', 0.0):.2f}</fe:ImpNeto>",
            f"        <fe:ImpOpEx>{data.get('ImpOpEx', 0.0):.2f}</fe:ImpOpEx>",
            f"        <fe:ImpTrib>{data.get('ImpTrib', 0.0):.2f}</fe:ImpTrib>",
            f"        <fe:ImpIVA>{data.get('ImpIVA', 0.0):.2f}</fe:ImpIVA>",
        ]

        # Fechas de servicio si concepto > 1
        if concepto in [2, 3]:
            fch_desde = data.get("FchServDesde") or data["CbteFch"]
            fch_hasta = data.get("FchServHasta") or data["CbteFch"]
            fch_vto = data.get("FchVtoPago") or data["CbteFch"]
            xml_parts.append(f"        <fe:FchServDesde>{fch_desde}</fe:FchServDesde>")
            xml_parts.append(f"        <fe:FchServHasta>{fch_hasta}</fe:FchServHasta>")
            xml_parts.append(f"        <fe:FchVtoPago>{fch_vto}</fe:FchVtoPago>")

        xml_parts.append(f"        <fe:MonId>{data.get('MonId', 'PES')}</fe:MonId>")
        xml_parts.append(f"        <fe:MonCotiz>{data.get('MonCotiz', 1.0):.2f}</fe:MonCotiz>")

        # Comprobantes Asociados
        cbtes_asoc = data.get("CbtesAsoc", [])
        if cbtes_asoc:
            xml_parts.append("        <fe:CbtesAsoc>")
            for asoc in cbtes_asoc:
                xml_parts.append("          <fe:CbteAsoc>")
                xml_parts.append(f"            <fe:Tipo>{asoc['Tipo']}</fe:Tipo>")
                xml_parts.append(f"            <fe:PtoVta>{asoc['PtoVta']}</fe:PtoVta>")
                xml_parts.append(f"            <fe:Nro>{asoc['Nro']}</fe:Nro>")
                if "Cuit" in asoc and asoc["Cuit"]:
                    xml_parts.append(f"            <fe:Cuit>{asoc['Cuit']}</fe:Cuit>")
                xml_parts.append("          </fe:CbteAsoc>")
            xml_parts.append("        </fe:CbtesAsoc>")

        # Tributos
        tributos = data.get("Tributos", [])
        if tributos:
            xml_parts.append("        <fe:Tributos>")
            for trib in tributos:
                xml_parts.append("          <fe:Tributo>")
                xml_parts.append(f"            <fe:Id>{trib['Id']}</fe:Id>")
                xml_parts.append(f"            <fe:Desc>{trib.get('Desc', '')}</fe:Desc>")
                xml_parts.append(f"            <fe:BaseImp>{trib['BaseImp']:.2f}</fe:BaseImp>")
                xml_parts.append(f"            <fe:Alic>{trib['Alic']:.2f}</fe:Alic>")
                xml_parts.append(f"            <fe:Importe>{trib['Importe']:.2f}</fe:Importe>")
                xml_parts.append("          </fe:Tributo>")
            xml_parts.append("        </fe:Tributos>")

        # IVA
        ivas = data.get("Iva", [])
        if ivas:
            xml_parts.append("        <fe:Iva>")
            for iva in ivas:
                xml_parts.append("          <fe:AlicIva>")
                xml_parts.append(f"            <fe:Id>{iva['Id']}</fe:Id>")
                xml_parts.append(f"            <fe:BaseImp>{iva['BaseImp']:.2f}</fe:BaseImp>")
                xml_parts.append(f"            <fe:Importe>{iva['Importe']:.2f}</fe:Importe>")
                xml_parts.append("          </fe:AlicIva>")
            xml_parts.append("        </fe:Iva>")

        # Opcionales
        opcionales = data.get("Opcionales", [])
        if opcionales:
            xml_parts.append("        <fe:Opcionales>")
            for opc in opcionales:
                xml_parts.append("          <fe:Opcional>")
                xml_parts.append(f"            <fe:Id>{opc['Id']}</fe:Id>")
                xml_parts.append(f"            <fe:Valor>{opc['Valor']}</fe:Valor>")
                xml_parts.append("          </fe:Opcional>")
            xml_parts.append("        </fe:Opcionales>")

        xml_parts.extend([
            "      </fe:FECAEDetRequest>",
            "    </fe:FeDetReq>",
            "  </fe:FeCAEReq>",
            "</fe:FECAESolicitar>",
        ])

        return "\n".join(xml_parts)
