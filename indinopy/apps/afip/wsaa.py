import logging
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from typing import Dict, Tuple
import requests
from django.core.cache import cache

logger = logging.getLogger(__name__)


class WSAAClient:
    """
    Cliente directo para el Web Service de Autenticación y Autorización (WSAA) de AFIP/ARCA.
    Genera el Ticket de Requerimiento de Acceso (TRA), lo firma digitalmente en formato PKCS#7 / CMS
    mediante OpenSSL y solicita el Token y Sign oficiales sin intermediarios externos.
    """

    URL_HOMO = "https://wsaahomo.afip.gov.ar/ws/services/LoginCms"
    URL_PROD = "https://wsaa.afip.gov.ar/ws/services/LoginCms"

    @classmethod
    def get_wsaa_url(cls, production: bool = False) -> str:
        return cls.URL_PROD if production else cls.URL_HOMO

    @classmethod
    def generar_tra_xml(cls, service: str = "wsfe", ttl_minutes: int = 720) -> str:
        """
        Genera el XML del Ticket de Requerimiento de Acceso (TRA).
        """
        now = datetime.now(timezone.utc)
        gen_time = now - timedelta(minutes=5)
        exp_time = now + timedelta(minutes=ttl_minutes)

        gen_time_str = gen_time.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        exp_time_str = exp_time.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        unique_id = str(int(now.timestamp()))

        tra = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<loginTicketRequest version="1.0">\n'
            "  <header>\n"
            f"    <uniqueId>{unique_id}</uniqueId>\n"
            f"    <generationTime>{gen_time_str}</generationTime>\n"
            f"    <expirationTime>{exp_time_str}</expirationTime>\n"
            "  </header>\n"
            f"  <service>{service}</service>\n"
            "</loginTicketRequest>"
        )
        return tra

    @classmethod
    def firmar_tra_cms(cls, tra_xml: str, cert_path: str, key_path: str) -> str:
        """
        Firma el XML del TRA en formato PKCS#7 (CMS) usando el certificado .crt y clave .key
        mediante openssl cms de forma nativa. Retorna el CMS codificado en Base64.
        """
        with tempfile.NamedTemporaryFile("w+", delete=True) as tra_file:
            tra_file.write(tra_xml)
            tra_file.flush()

            cmd = [
                "openssl",
                "cms",
                "-sign",
                "-in",
                tra_file.name,
                "-signer",
                cert_path,
                "-inkey",
                key_path,
                "-outform",
                "DER",
                "-nodetach",
            ]

            process = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            if process.returncode != 0:
                err_msg = process.stderr.decode("utf-8", errors="replace")
                raise ValueError(f"Error firmando TRA con OpenSSL: {err_msg}")

            import base64
            cms_der = process.stdout
            return base64.b64encode(cms_der).decode("ascii")

    @classmethod
    def solicitar_login_cms(cls, cms_b64: str, production: bool = False) -> Tuple[str, str]:
        """
        Envía el CMS firmado al endpoint LoginCms del WSAA y extrae Token y Sign.
        """
        url = cls.get_wsaa_url(production=production)

        soap_request = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" '
            'xmlns:wsaa="http://wsaa.view.sua.dvadac.desein.afip.gov">\n'
            "  <soapenv:Header/>\n"
            "  <soapenv:Body>\n"
            "    <wsaa:loginCms>\n"
            f"      <wsaa:in0>{cms_b64}</wsaa:in0>\n"
            "    </wsaa:loginCms>\n"
            "  </soapenv:Body>\n"
            "</soapenv:Envelope>"
        )

        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": "",
        }

        resp = requests.post(url, data=soap_request, headers=headers, timeout=15)
        if resp.status_code != 200:
            raise ValueError(
                f"Error en comunicación con WSAA (HTTP {resp.status_code}): {resp.text}"
            )

        root = ET.fromstring(resp.text)
        # Buscar loginCmsReturn ignorando namespaces
        login_return_elem = None
        for elem in root.iter():
            if elem.tag.endswith("loginCmsReturn"):
                login_return_elem = elem
                break

        if login_return_elem is None or not login_return_elem.text:
            raise ValueError(f"Respuesta inesperada de WSAA: {resp.text}")

        login_ticket_response = login_return_elem.text
        ta_root = ET.fromstring(login_ticket_response)

        token_elem = ta_root.find(".//token")
        sign_elem = ta_root.find(".//sign")

        if token_elem is None or sign_elem is None:
            raise ValueError(f"WSAA no devolvió token/sign válidos: {login_ticket_response}")

        return token_elem.text, sign_elem.text

    @classmethod
    def obtener_credenciales_servicio(
        cls,
        cuit: int,
        cert_path: str,
        key_path: str,
        service: str = "wsfe",
        production: bool = False,
        forzar_renovacion: bool = False,
    ) -> Dict[str, str]:
        """
        Obtiene Token y Sign vigentes para el servicio indicado.
        Aplica política de caché de 11 horas para minimizar peticiones al WSAA.
        """
        cache_key = f"afip:wsaa:{cuit}:{service}:{'prod' if production else 'homo'}"

        if not forzar_renovacion:
            cached_data = cache.get(cache_key)
            if cached_data:
                return cached_data

        if not cert_path or not key_path:
            raise ValueError(
                "No se especificaron certificados válidos (.crt / .key) para autenticar en AFIP."
            )

        tra_xml = cls.generar_tra_xml(service=service)
        cms_b64 = cls.firmar_tra_cms(tra_xml, cert_path=cert_path, key_path=key_path)
        token, sign = cls.solicitar_login_cms(cms_b64, production=production)

        creds = {
            "token": token,
            "sign": sign,
            "cuit": str(cuit),
        }

        # Guardar en caché con expiración de 11 horas (el ticket dura 12 horas)
        cache.set(cache_key, creds, timeout=11 * 3600)
        logger.info(f"Nuevo Ticket de Acceso (TA) obtenido exitosamente en WSAA para {service}.")
        return creds
