import logging
import xml.etree.ElementTree as ET
from typing import Dict, Any, Optional
import requests
from django.core.cache import cache
from .dtos import ContribuyentePadronDTO

logger = logging.getLogger(__name__)


class PadronA13Client:
    """
    Cliente SOAP nativo para el Web Service de Consulta a Padrón - Alcance 13 (personaServiceA13)
    de ARCA (ex-AFIP).
    Permite consultar el estado de la clave, datos generales, condición frente al IVA y Monotributo.
    """

    URL_HOMO = "https://awshomo.afip.gov.ar/sr-padron/webservices/personaServiceA13"
    URL_PROD = "https://aws.afip.gov.ar/sr-padron/webservices/personaServiceA13"
    SOAP_NS = "http://a13.soap.ws.server.puc.sr/"

    def __init__(self, token: str, sign: str, cuit_representada: int, production: bool = False):
        self.token = token
        self.sign = sign
        self.cuit_representada = cuit_representada
        self.production = production
        self.endpoint = self.URL_PROD if production else self.URL_HOMO

    def _ejecutar_soap(self, action: str, body_xml: str) -> ET.Element:
        envelope = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
            f'xmlns:a13="{self.SOAP_NS}">\n'
            "  <soapenv:Header/>\n"
            "  <soapenv:Body>\n"
            f"    {body_xml}\n"
            "  </soapenv:Body>\n"
            "</soapenv:Envelope>"
        )

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": "",
        }

        resp = requests.post(self.endpoint, data=envelope.encode("utf-8"), headers=headers, timeout=15)
        if resp.status_code != 200:
            raise ValueError(f"Error HTTP en llamada a Padrón A13 {action} ({resp.status_code}): {resp.text}")

        return ET.fromstring(resp.text)

    def get_taxpayer_details(self, id_persona: int) -> Dict[str, Any]:
        """
        Consulta los datos fiscales de una persona física o jurídica (getPersona).
        Retorna diccionario con estructura compatible con PadronAFIPService.
        """
        body_xml = (
            "<a13:getPersona>\n"
            f"  <token>{self.token}</token>\n"
            f"  <sign>{self.sign}</sign>\n"
            f"  <cuitRepresentada>{self.cuit_representada}</cuitRepresentada>\n"
            f"  <idPersona>{id_persona}</idPersona>\n"
            "</a13:getPersona>"
        )

        root = self._ejecutar_soap("getPersona", body_xml)

        persona_elem = None
        for elem in root.iter():
            if elem.tag.endswith("personaReturn"):
                persona_elem = elem
                break

        if persona_elem is None:
            raise ValueError("Respuesta vacía de Padrón A13.")

        return self._xml_a_dict(persona_elem)

    def _xml_a_dict(self, element: ET.Element) -> Dict[str, Any]:
        tag = element.tag.split("}")[-1] if "}" in element.tag else element.tag
        result = {}

        if list(element):
            for child in element:
                child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                child_val = self._xml_a_dict(child)

                if child_tag in result:
                    if not isinstance(result[child_tag], list):
                        result[child_tag] = [result[child_tag]]
                    result[child_tag].append(child_val)
                else:
                    result[child_tag] = child_val
        else:
            return element.text or ""

        return result


class PadronAFIPService:
    """
    Servicio de alto nivel para consultar el estado tributario, domicilio y condición frente al IVA
    de un CUIT/CUIL a través del webservice de Padrón de AFIP/ARCA con política de caché.
    """

    CACHE_TTL_SECONDS = 60 * 60 * 24  # 24 horas

    @classmethod
    def consultar_cuit(cls, cuit: str, usar_cache: bool = True) -> Optional[ContribuyentePadronDTO]:
        cuit_str = str(cuit).replace("-", "").strip()
        if not cuit_str or len(cuit_str) != 11 or not cuit_str.isdigit():
            raise ValueError(f"El CUIT ingresado '{cuit}' no es válido (debe tener 11 dígitos).")

        cache_key = f"afip:padron:{cuit_str}"
        if usar_cache:
            cached_data = cache.get(cache_key)
            if cached_data:
                logger.info(f"Retornando datos de padrón AFIP desde caché para CUIT {cuit_str}")
                return cached_data

        from .client import AFIPClientFactory
        afip = AFIPClientFactory.get_client()

        raw_res = None
        errores = []

        try:
            if hasattr(afip, "RegisterScopeThirteen"):
                raw_res = afip.RegisterScopeThirteen.getTaxpayerDetails(int(cuit_str))
        except Exception as e:
            errores.append(f"Padrón A13: {e}")

        if not raw_res:
            logger.error(f"No se pudo consultar el CUIT {cuit_str} en el padrón de AFIP: {'; '.join(errores)}")
            return None

        dto = cls._normalizar_respuesta(cuit_str, raw_res)

        if usar_cache and dto:
            cache.set(cache_key, dto, timeout=cls.CACHE_TTL_SECONDS)

        return dto

    @classmethod
    def _normalizar_respuesta(cls, cuit_str: str, data: dict) -> ContribuyentePadronDTO:
        datos_generales = data.get("datosGenerales", {}) or data

        razon_social = datos_generales.get("razonSocial")
        if not razon_social:
            apellido = datos_generales.get("apellido", "") or ""
            nombre = datos_generales.get("nombre", "") or ""
            razon_social = f"{apellido} {nombre}".strip() or "Sin Identificar"

        tipo_persona = datos_generales.get("tipoPersona", "FISICA")
        estado_clave = datos_generales.get("estadoClave", "ACTIVO")

        # Domicilio Fiscal
        domicilio = datos_generales.get("domicilioFiscal", {}) or {}
        direccion = domicilio.get("direccion", "")
        localidad = domicilio.get("localidad", "")
        provincia = domicilio.get("descripcionProvincia", "")
        cp = str(domicilio.get("codPostal", ""))

        # Condición frente al IVA
        condicion_iva = "CONSUMIDOR_FINAL"
        categoria_monotributo = None
        es_monotributista = False
        es_responsable_inscripto = False
        es_exento = False

        datos_monotributo = data.get("datosMonotributo")
        datos_regimen_general = data.get("datosRegimenGeneral")

        impuestos_ids = []
        if datos_regimen_general:
            impuestos = datos_regimen_general.get("impuesto", [])
            if isinstance(impuestos, list):
                impuestos_ids = [imp.get("idImpuesto") for imp in impuestos if isinstance(imp, dict)]
            elif isinstance(impuestos, dict):
                impuestos_ids = [impuestos.get("idImpuesto")]

            # 30 = IVA, 32 = IVA Exento
            if 30 in impuestos_ids:
                condicion_iva = "RESPONSABLE_INSCRIPTO"
                es_responsable_inscripto = True
            elif 32 in impuestos_ids:
                condicion_iva = "EXENTO"
                es_exento = True

        if datos_monotributo and not es_responsable_inscripto:
            condicion_iva = "RESPONSABLE_MONOTRIBUTO"
            es_monotributista = True
            cat_obj = datos_monotributo.get("categoriaMonotributo", {})
            if isinstance(cat_obj, dict):
                categoria_monotributo = cat_obj.get("descripcionCategoria")

        # Actividades
        actividades = []
        act_data = datos_regimen_general.get("actividad", []) if datos_regimen_general else []
        if isinstance(act_data, list):
            actividades = [a.get("descripcionActividad", "") for a in act_data if isinstance(a, dict)]
        elif isinstance(act_data, dict):
            actividades = [act_data.get("descripcionActividad", "")]

        return ContribuyentePadronDTO(
            cuit=cuit_str,
            nombre_razon_social=razon_social,
            tipo_persona=tipo_persona,
            estado_clave=estado_clave,
            condicion_iva=condicion_iva,
            categoria_monotributo=categoria_monotributo,
            es_monotributista=es_monotributista,
            es_responsable_inscripto=es_responsable_inscripto,
            es_exento=es_exento,
            direccion=direccion,
            localidad=localidad,
            provincia=provincia,
            codigo_postal=cp,
            impuestos_activos=impuestos_ids,
            actividades=actividades,
            raw_data=data,
        )
