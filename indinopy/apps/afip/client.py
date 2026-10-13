import logging
from typing import Optional, Dict, Any
from django.core.exceptions import ImproperlyConfigured
from apps.base.models import ConfiguracionEmpresa
from .wsaa import WSAAClient
from .wsfe import WSFEClient

logger = logging.getLogger(__name__)


class ElectronicBillingProxy:
    """
    Proxy que provee los métodos getLastVoucher y createVoucher directamente
    hacia WSFEv1 sin intermediarios.
    """

    def __init__(self, wsfe_client: WSFEClient):
        self._wsfe = wsfe_client

    def getLastVoucher(self, pto_vta: int, tipo_cbte: int) -> int:
        return self._wsfe.get_last_voucher(pto_vta, tipo_cbte)

    def createVoucher(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return self._wsfe.create_voucher(data)


class AFIPClientDirecto:
    """
    Cliente nativo directo de AFIP/ARCA. Reemplaza el objeto de afip-py
    sin requerir servidores externos intermediarios.
    """

    def __init__(self, cuit: int, cert_path: Optional[str], key_path: Optional[str], production: bool = False):
        self.cuit = cuit
        self.cert_path = cert_path
        self.key_path = key_path
        self.production = production
        self._electronic_billing: Optional[ElectronicBillingProxy] = None

    @property
    def ElectronicBilling(self) -> ElectronicBillingProxy:
        if self._electronic_billing is None:
            creds = WSAAClient.obtener_credenciales_servicio(
                cuit=self.cuit,
                cert_path=self.cert_path or "",
                key_path=self.key_path or "",
                service="wsfe",
                production=self.production,
            )
            wsfe_client = WSFEClient(
                token=creds["token"],
                sign=creds["sign"],
                cuit=self.cuit,
                production=self.production,
            )
            self._electronic_billing = ElectronicBillingProxy(wsfe_client)
        return self._electronic_billing

    @property
    def RegisterScopeThirteen(self):
        """
        Proxy nativo para Padrón Alcance 13 (personaServiceA13).
        """
        from .padron import PadronA13Client

        creds = WSAAClient.obtener_credenciales_servicio(
            cuit=self.cuit,
            cert_path=self.cert_path or "",
            key_path=self.key_path or "",
            service="ws_sr_padron_a13",
            production=self.production,
        )
        padron_client = PadronA13Client(
            token=creds["token"],
            sign=creds["sign"],
            cuit_representada=self.cuit,
            production=self.production,
        )

        class PadronProxy:
            def getTaxpayerDetails(self, id_persona: int):
                return padron_client.get_taxpayer_details(id_persona)

        return PadronProxy()

    @property
    def ComprobanteConstatacion(self):
        """
        Proxy nativo para Constatación de Comprobantes WSCDC.
        """
        from .cdc_client import CDCClient

        creds = WSAAClient.obtener_credenciales_servicio(
            cuit=self.cuit,
            cert_path=self.cert_path or "",
            key_path=self.key_path or "",
            service="wscdc",
            production=self.production,
        )
        return CDCClient(
            token=creds["token"],
            sign=creds["sign"],
            cuit_consultante=self.cuit,
            production=self.production,
        )


class AFIPClientFactory:
    """
    Factoría y gestor de instancia para el cliente nativo de AFIP.
    Inicializa directamente con las credenciales del Singleton ConfiguracionEmpresa.
    """

    @classmethod
    def get_client(cls) -> AFIPClientDirecto:
        config = ConfiguracionEmpresa.get_solo()

        if not config.cuit:
            raise ImproperlyConfigured(
                "La Configuración de Empresa no tiene CUIT configurado."
            )

        cuit_limpio = int(str(config.cuit).replace("-", "").strip())

        cert_path = config.afip_certificado.path if config.afip_certificado else None
        key_path = config.afip_clave_privada.path if config.afip_clave_privada else None

        if not cert_path or not key_path:
            logger.warning(
                "Faltan certificados AFIP (.crt/.key) en la Configuración de Empresa. Las llamadas a AFIP fallarán."
            )

        return AFIPClientDirecto(
            cuit=cuit_limpio,
            cert_path=cert_path,
            key_path=key_path,
            production=config.afip_entorno == "produccion",
        )
