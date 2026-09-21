import logging
from django.core.exceptions import ImproperlyConfigured
from apps.base.models import ConfiguracionEmpresa
from afip import Afip

logger = logging.getLogger(__name__)


class AFIPClientFactory:
    """
    Factoría y gestor de instancia para afip-py.
    Asegura inicialización centralizada con las credenciales activas del Singleton ConfiguracionEmpresa.
    """

    @classmethod
    def get_client(cls) -> Afip:
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

        return Afip(
            {
                "CUIT": cuit_limpio,
                "cert": cert_path,
                "key": key_path,
                "production": config.afip_entorno == "produccion",
            }
        )
