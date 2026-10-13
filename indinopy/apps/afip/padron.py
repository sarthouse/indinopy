import logging
from typing import Optional
from django.core.cache import cache
from .client import AFIPClientFactory
from .dtos import ContribuyentePadronDTO

logger = logging.getLogger(__name__)


class PadronAFIPService:
    """
    Servicio para consultar el estado tributario, domicilio y condición frente al IVA
    de un CUIT/CUIL a través del webservice de Padrón de AFIP (WSSR Alcance 13 / Alcance 10 / A5).
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

        afip = AFIPClientFactory.get_client()

        # Intentar consultar con Alcance 13 o Alcance 10
        raw_res = None
        errores = []

        # 1. Probar RegisterScopeThirteen (A13)
        try:
            if hasattr(afip, "RegisterScopeThirteen"):
                raw_res = afip.RegisterScopeThirteen.getTaxpayerDetails(int(cuit_str))
        except Exception as e:
            errores.append(f"Alcance 13: {e}")

        # 2. Si falla o no está disponible, intentar con RegisterScopeTen (A10)
        if not raw_res:
            try:
                if hasattr(afip, "RegisterScopeTen"):
                    raw_res = afip.RegisterScopeTen.getTaxpayerDetails(int(cuit_str))
            except Exception as e:
                errores.append(f"Alcance 10: {e}")

        # 3. Si falla, intentar RegisterScopeFour (A4 / A5)
        if not raw_res:
            try:
                if hasattr(afip, "RegisterScopeFour"):
                    raw_res = afip.RegisterScopeFour.getTaxpayerDetails(int(cuit_str))
            except Exception as e:
                errores.append(f"Alcance 4: {e}")

        if not raw_res:
            logger.error(f"No se pudo consultar el CUIT {cuit_str} en los padrones de AFIP: {'; '.join(errores)}")
            return None

        dto = cls._normalizar_respuesta(cuit_str, raw_res)

        if usar_cache and dto:
            cache.set(cache_key, dto, timeout=cls.CACHE_TTL_SECONDS)

        return dto

    @classmethod
    def _normalizar_respuesta(cls, cuit_str: str, data: dict) -> ContribuyentePadronDTO:
        # Extraer nombre o razón social
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
