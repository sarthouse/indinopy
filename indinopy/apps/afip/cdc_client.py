import logging
import xml.etree.ElementTree as ET
from typing import Dict, Any, Optional
import requests

logger = logging.getLogger(__name__)


class CDCClient:
    """
    Cliente SOAP nativo para el Web Service de Constatación de Comprobantes (WSCDC) de ARCA (ex-AFIP).
    Permite verificar la existencia y validez de un comprobante con CAE/CAI/CAEA.
    """

    URL_HOMO = "https://wswhomo.arca.gov.ar/WSCDC/service.asmx"
    URL_PROD = "https://servicios1.arca.gov.ar/WSCDC/service.asmx"
    SOAP_NS = "http://ar.gov.afip.dif.WSCDC/"

    def __init__(self, token: str, sign: str, cuit_consultante: int, production: bool = False):
        self.token = token
        self.sign = sign
        self.cuit_consultante = cuit_consultante
        self.production = production
        self.endpoint = self.URL_PROD if production else self.URL_HOMO

    def _ejecutar_soap(self, action: str, body_xml: str) -> ET.Element:
        envelope = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
            f'xmlns:cdc="{self.SOAP_NS}">\n'
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

        resp = requests.post(self.endpoint, data=envelope.encode("utf-8"), headers=headers, timeout=15)
        if resp.status_code != 200:
            raise ValueError(f"Error HTTP en llamada a WSCDC {action} ({resp.status_code}): {resp.text}")

        return ET.fromstring(resp.text)

    def constatar_comprobante(
        self,
        cuit_emisor: int,
        pto_vta: int,
        cbte_tipo: int,
        cbte_nro: int,
        cbte_fch: str,  # Formato YYYYMMDD
        imp_total: float,
        cae: str,
        doc_tipo_receptor: int = 80,  # 80 = CUIT, 99 = Consumidor Final
        doc_nro_receptor: int = 0,
    ) -> Dict[str, Any]:
        """
        Ejecuta el método ComprobanteConstatar de WSCDC.
        Retorna:
          {
            "resultado": "A" (Aprobado/Constatado) o "R" (Rechazado/Inexistente),
            "cae": cae,
            "observaciones": [...],
            "errores": [...]
          }
        """
        body_xml = (
            "<cdc:ComprobanteConstatar>\n"
            "  <cdc:Auth>\n"
            f"    <cdc:Token>{self.token}</cdc:Token>\n"
            f"    <cdc:Sign>{self.sign}</cdc:Sign>\n"
            f"    <cdc:Cuit>{self.cuit_consultante}</cdc:Cuit>\n"
            "  </cdc:Auth>\n"
            "  <cdc:CmpReq>\n"
            f"    <cdc:CbteModo>CAE</cdc:CbteModo>\n"
            f"    <cdc:CuitEmisor>{cuit_emisor}</cdc:CuitEmisor>\n"
            f"    <cdc:PtoVta>{pto_vta}</cdc:PtoVta>\n"
            f"    <cdc:CbteTipo>{cbte_tipo}</cdc:CbteTipo>\n"
            f"    <cdc:CbteNro>{cbte_nro}</cdc:CbteNro>\n"
            f"    <cdc:CbteFch>{cbte_fch}</cdc:CbteFch>\n"
            f"    <cdc:ImpTotal>{imp_total:.2f}</cdc:ImpTotal>\n"
            f"    <cdc:CodAutorizacion>{cae}</cdc:CodAutorizacion>\n"
            f"    <cdc:DocTipoReceptor>{doc_tipo_receptor}</cdc:DocTipoReceptor>\n"
            f"    <cdc:DocNroReceptor>{doc_nro_receptor}</cdc:DocNroReceptor>\n"
            "  </cdc:CmpReq>\n"
            "</cdc:ComprobanteConstatar>"
        )

        root = self._ejecutar_soap("ComprobanteConstatar", body_xml)

        resultado_elem = root.find(".//{http://ar.gov.afip.dif.WSCDC/}Resultado")
        resultado = resultado_elem.text if resultado_elem is not None else "R"

        # Observaciones
        observaciones = []
        for obs in root.findall(".//{http://ar.gov.afip.dif.WSCDC/}Obs"):
            code = obs.findtext("{http://ar.gov.afip.dif.WSCDC/}Code", "")
            msg = obs.findtext("{http://ar.gov.afip.dif.WSCDC/}Msg", "")
            observaciones.append(f"[{code}] {msg}")

        # Errores
        errores = []
        for err in root.findall(".//{http://ar.gov.afip.dif.WSCDC/}Err"):
            code = err.findtext("{http://ar.gov.afip.dif.WSCDC/}Code", "")
            msg = err.findtext("{http://ar.gov.afip.dif.WSCDC/}Msg", "")
            errores.append(f"[{code}] {msg}")

        return {
            "resultado": resultado,
            "es_valido": resultado == "A",
            "cae": cae,
            "observaciones": observaciones,
            "errores": errores,
        }
