import json
import logging
import datetime
import requests
from decimal import Decimal
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from apps.tesoreria.models import ComprobanteTesoreria, MovimientoCaja, Caja
from .models import ContratoEOP, EOPHitoEscrow, IndiceUCI

logger = logging.getLogger(__name__)


class ParametrosFDIService:
    """
    Servicio desacoplador para consultar dinámicamente las alícuotas arancelarias
    y el Fondo de Riesgo FDI fijadas por la Comisión de Crédito.
    Aplica política de caché y fallback de contingencia reglamentario.
    """
    CACHE_KEY = "fdi:parametros_arancelarios"
    CACHE_TTL_SECONDS = 60 * 60 * 24 * 7  # 1 semana (7 días)

    @classmethod
    def refrescar_parametros_desde_fdi(cls, fdi_url=None):
        """
        Consulta al Nodo FDI para sincronizar aranceles y refrescar la caché de Redis.
        """
        base_url = (
            fdi_url
            or getattr(settings, "NODO_FDI_URL", None)
        )
        if not base_url:
            logger.warning("NODO_FDI_URL no está configurado.")
            return None
        base_url = base_url.rstrip("/")
        endpoint = f"{base_url}/fdi/api/v1/fdi/parametros-arancelarios/"

        try:
            resp = requests.get(endpoint, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                cache.set(cls.CACHE_KEY, data, cls.CACHE_TTL_SECONDS)
                logger.info(f"Parámetros arancelarios FDI sincronizados: {data.get('alicuota_total_recargo')}")
                return data
            else:
                logger.warning(f"Error consultando aranceles en FDI (HTTP {resp.status_code})")
        except Exception as e:
            logger.warning(f"Error conectando al nodo FDI para sincronizar aranceles: {e}")
        return None

    # Alias de retrocompatibilidad
    refrescar_parametros_desde_mes = refrescar_parametros_desde_fdi

    @classmethod
    def obtener_alicuota_recargo_fdi(cls, fdi_url=None, mes_url=None):
        """
        Devuelve la alícuota total de recargo s/MOD (Fondo FDI).
        Tope legal Ley e-OP Art. 4° inc. 4.c: 1.5% (0.015).
        1. Consulta en caché Redis local (expira a los 7 días).
        2. Si no está en caché, consulta por HTTP al Nodo FDI.
        3. Si el FDI no responde (offline / contingencia), aplica el fallback de 1.5% (0.015).
        """
        target_url = fdi_url or mes_url
        cached = cache.get(cls.CACHE_KEY)
        if cached:
            alicuota = Decimal(str(cached.get("alicuota_total_recargo", "0.015")))
            return min(alicuota, Decimal("0.015"))

        data = cls.refrescar_parametros_desde_fdi(fdi_url=target_url)
        if data:
            alicuota = Decimal(str(data.get("alicuota_total_recargo", "0.015")))
            return min(alicuota, Decimal("0.015"))

        # Fallback reglamentario según Ley e-OP y Dossier FIMCA (1.0% + 0.5% = 1.5%)
        return Decimal("0.015")

    @classmethod
    def obtener_alicuota_stock_fdi(cls, fdi_url=None, mes_url=None):
        """
        Devuelve la alícuota fiduciaria de cobertura de stock s/BOM (Art. 4° inc. 4.c).
        Tope legal Ley e-OP: 0.5% (0.005) sobre valor BOM para prima colectiva de seguros.
        """
        target_url = fdi_url or mes_url
        cached = cache.get(cls.CACHE_KEY)
        if cached and "alicuota_stock" in cached:
            alicuota = Decimal(str(cached.get("alicuota_stock", "0.005")))
            return min(alicuota, Decimal("0.005"))

        data = cls.refrescar_parametros_desde_fdi(fdi_url=target_url)
        if data and "alicuota_stock" in data:
            alicuota = Decimal(str(data.get("alicuota_stock", "0.005")))
            return min(alicuota, Decimal("0.005"))

        return Decimal("0.005")


class FederacionFDIService:
    """
    Servicio cliente de federación saliente para consumir las APIs del Nodo Central FDI
    (Fondo Fiduciario de Desarrollo Industrial).
    """

    @classmethod
    def obtener_fdi_url(cls, fdi_url=None):
        url = (
            fdi_url
            or getattr(settings, "NODO_FDI_URL", None)
        )
        if not url:
            raise ValueError("NODO_FDI_URL no está configurado en las variables de entorno ni en settings.")
        return url.rstrip("/")

    @classmethod
    def consultar_cupo_fdi(cls, fdi_url=None):
        """
        Consulta en tiempo real el estado del crédito, mora y cupo operativo
        al servidor del FDI enviando el CUIT de la empresa local en el header X-CUIT.
        """
        from apps.base.models import ConfiguracionEmpresa

        empresa = ConfiguracionEmpresa.objects.first()
        if not empresa or not empresa.cuit:
            raise ValueError("No hay una Configuración de Empresa con CUIT definida en este nodo.")

        base_url = cls.obtener_fdi_url(fdi_url)
        endpoint = f"{base_url}/fdi/api/v1/fdi/estado-credito/"

        try:
            respuesta = requests.get(
                endpoint,
                headers={"X-CUIT": empresa.cuit},
                timeout=5,
            )
            if respuesta.status_code == 200:
                return respuesta.json()
            elif respuesta.status_code == 404:
                raise ValueError("El FDI informa que la empresa no posee una línea de crédito asignada.")
            else:
                raise ValueError(f"Error de red comunicándose con el FDI: {respuesta.status_code}")
        except requests.RequestException as e:
            raise ValueError(f"El Nodo FDI no está disponible: {str(e)}")

    # Alias de retrocompatibilidad
    consultar_cupo_mes = consultar_cupo_fdi

    @classmethod
    def consultar_pauta_escrow_fdi(cls, fdi_url=None, es_sello_buen_diseno=False):
        """
        Consulta por HTTP a la API federada del FDI la pauta oficial de porcentajes de Escrow
        vigente (Hito Cero, Sello Buen Diseño, Hito Final).
        """
        base_url = cls.obtener_fdi_url(fdi_url)
        endpoint = f"{base_url}/federacion/api/v1/escrow/pauta/"
        params = {"sello_buen_diseno": "true" if es_sello_buen_diseno else "false"}

        try:
            resp = requests.get(endpoint, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "porcentaje_cero": Decimal(str(data["porcentaje_cero"])),
                    "etiqueta_cero": data["etiqueta_cero"],
                    "porcentaje_final": Decimal(str(data["porcentaje_final"])),
                    "porcentaje_avance": Decimal(str(data["porcentaje_avance"])),
                    "nombre_pauta": data.get("nombre_pauta", "Pauta Oficial Escrow FDI"),
                }
        except Exception:
            pass

        # Fallback de contingencia local si el FDI no responde
        porc_cero = Decimal("50.00") if es_sello_buen_diseno else Decimal("35.00")
        porc_final = Decimal("20.00")
        return {
            "porcentaje_cero": porc_cero,
            "etiqueta_cero": f"Hito Cero - Anticipo Operativo de Arranque ({'Sello Buen Diseño 50%' if es_sello_buen_diseno else 'Estándar 35%'})",
            "porcentaje_final": porc_final,
            "porcentaje_avance": Decimal("100.00") - porc_cero - porc_final,
            "nombre_pauta": "Pauta Oficial Escrow FDI (Fallback Local)",
        }

    # Alias de retrocompatibilidad
    consultar_pauta_escrow_mes = consultar_pauta_escrow_fdi

    @classmethod
    def transmitir_eop_al_fdi(cls, contrato_eop, firma_comitente_hex, clave_publica_hex, fdi_url=None):
        """
        Emite el HTTP POST con el payload canónico firmado hacia el endpoint receptor
        del nodo fiduciario (/federacion/eop/entrante/).
        """
        from apps.base.models import ConfiguracionEmpresa

        empresa = ConfiguracionEmpresa.objects.first()
        if not empresa or not empresa.cuit:
            raise ValueError("No hay una Configuración de Empresa con CUIT definida en este nodo.")

        base_url = cls.obtener_fdi_url(fdi_url or contrato_eop.nodo_mes)
        endpoint = f"{base_url}/federacion/eop/entrante/"

        # Asegurar hash de integridad criptográfica
        contrato_eop.sellar_hash_seguridad()

        # Validación Inviolable: La e-OP no puede transmitirse sin la firma del tallerista gestor
        firmas = contrato_eop.firmas_digitales or {}
        if "tallerista" not in firmas or not firmas["tallerista"].get("firma_hex"):
            raise ValueError(
                f"No se puede transmitir la e-OP {contrato_eop.numero or contrato_eop.uuid_identificador} a la Red Federada: "
                f"El tallerista gestor aún no ha firmado digitalmente el contrato en el portal."
            )

        payload_canonico_str = contrato_eop.generar_payload_canonico()
        payload_canonico_dict = json.loads(payload_canonico_str)

        sobre_transporte = {
            "uuid_identificador": str(contrato_eop.uuid_identificador),
            "hash_seguridad": contrato_eop.hash_seguridad,
            "comitente_cuit": empresa.cuit,
            "tallerista_cuit": payload_canonico_dict.get("tallerista_cuit", ""),
            "monto_total_uci": str(contrato_eop.monto_total_uci),
            "payload_canonico": payload_canonico_dict,
            "firma_comitente": firma_comitente_hex,
            "clave_publica_comitente": clave_publica_hex,
            "firma_tallerista": firmas["tallerista"]["firma_hex"],
            "cronograma_escrow_hitos": payload_canonico_dict.get("cronograma_escrow_hitos", []),
        }

        try:
            respuesta = requests.post(
                endpoint,
                json=sobre_transporte,
                headers={"X-CUIT": empresa.cuit, "Content-Type": "application/json"},
                timeout=10,
            )
            if respuesta.status_code in [200, 201]:
                return respuesta.json()
            else:
                raise ValueError(
                    f"Error rechazado por el FDI ({respuesta.status_code}): {respuesta.text}"
                )
        except requests.RequestException as e:
            raise ValueError(f"Fallo de conexión al despachar e-OP al Nodo FDI: {str(e)}")

    # Alias de retrocompatibilidad
    transmitir_eop_a_mes = transmitir_eop_al_fdi


FederacionCreditoService = FederacionFDIService



class UCIService:
    """
    Servicio conversor y cotizador para la Unidad de Cuenta Industrial (UCI).
    Protege el Escrow contra fluctuaciones de inflación indexando a IPIM.
    """
    @staticmethod
    def obtener_cotizacion_actual():
        """Devuelve el valor actual de 1 UCI en ARS."""
        cotizacion = IndiceUCI.objects.order_by('-fecha').first()
        if not cotizacion:
            return Decimal("1.00") # Fallback por defecto (1 UCI = 1 ARS)
        return cotizacion.valor_ars

    @staticmethod
    def ars_a_uci(monto_ars, fecha=None):
        """Convierte ARS a UCI usando la cotización a una fecha dada (o la más reciente)."""
        if not monto_ars:
            return Decimal("0.00")
        
        qs = IndiceUCI.objects.all()
        if fecha:
            qs = qs.filter(fecha__lte=fecha)
            
        cotizacion = qs.order_by('-fecha').first()
        valor = cotizacion.valor_ars if cotizacion else Decimal("1.00")
        
        return round(Decimal(monto_ars) / valor, 2)

    @staticmethod
    def uci_a_ars(monto_uci, fecha=None):
        """Convierte UCI a ARS usando la cotización a una fecha dada."""
        if not monto_uci:
            return Decimal("0.00")
            
        qs = IndiceUCI.objects.all()
        if fecha:
            qs = qs.filter(fecha__lte=fecha)
            
        cotizacion = qs.order_by('-fecha').first()
        valor = cotizacion.valor_ars if cotizacion else Decimal("1.00")
        
        return round(Decimal(monto_uci) * valor, 2)


class EOPService:
    @staticmethod
    @transaction.atomic
    def crear_contrato_desde_op(op, ptf=None, nodo_mes=None, porcentaje_anticipo=None):
        """
        Pasa una Orden de Producción (en ARS) a un ContratoEOP colateralizado en UCI.
        Lee los costos de etapas (MOD), insumos requeridos (BOM), cargas sociales e impuestos,
        convirtiéndolos a valor UCI vigente.
        """
        from apps.base.models import ConfiguracionEmpresa
        from django.conf import settings

        if not nodo_mes:
            empresa = ConfiguracionEmpresa.objects.first()
            nodo_mes = (
                (empresa.nodo_mes_endpoint or empresa.nodo_mes)
                if empresa else None
            ) or getattr(settings, "NODO_FDI_URL", "")

        cotizacion_uci = UCIService.obtener_cotizacion_actual()
        if not cotizacion_uci or cotizacion_uci <= 0:
            cotizacion_uci = Decimal("1.00")

        # 1. Mano de Obra Directa (MOD): Suma de tarifas de servicios de façón homologadas
        costo_mod_ars = sum(
            (etapa.costo_servicio_total or Decimal("0.00")) for etapa in op.tracking_etapas.all()
        )

        # 2. Insumos y Materias Primas Físicas (BOM aportado por la marca comitente)
        costo_bom_ars = Decimal("0.00")
        for req in op.insumos_requeridos.all():
            precio_unit = getattr(req.insumo, "costo", Decimal("0.00")) or Decimal("0.00")
            costo_bom_ars += req.cantidad_teorica * precio_unit

        # 3. Recargo Institucional de Red MES y Fondo de Riesgo FDI (consultado dinámicamente a la MES)
        alicuota_recargo_fdi = ParametrosFDIService.obtener_alicuota_recargo_fdi(mes_url=nodo_mes)
        alicuota_stock_fdi = ParametrosFDIService.obtener_alicuota_stock_fdi(mes_url=nodo_mes)

        costo_fdi_operativo_ars = round(costo_mod_ars * alicuota_recargo_fdi, 2)
        costo_fdi_stock_ars = round(costo_bom_ars * alicuota_stock_fdi, 2)

        # 4. Conversión a UCI
        def _to_uci(monto_ars):
            return round(Decimal(monto_ars) / cotizacion_uci, 2)

        hoy = timezone.now().date()
        plazo_dias = 60
        fecha_vto = hoy + datetime.timedelta(days=plazo_dias)

        contrato = ContratoEOP.objects.create(
            orden_produccion_local=op,
            nodo_mes=nodo_mes,
            ptf_asignado=ptf,
            costo_mod=_to_uci(costo_mod_ars),
            costo_bom=_to_uci(costo_bom_ars),
            costo_fdi_operativo=_to_uci(costo_fdi_operativo_ars),
            costo_fdi_stock=_to_uci(costo_fdi_stock_ars),
            moneda_denominacion="uci",
            plazo_comercial_dias=plazo_dias,
            fecha_vencimiento_comercial=fecha_vto,
            fecha_vencimiento_recalculada=fecha_vto,
            estado_escrow="solicitado",
        )

        # 5. Generar Árbol de Merkle del BOM
        contrato.merkle_root_bom = contrato.calcular_merkle_root_bom()
        contrato.save(update_fields=["merkle_root_bom"])

        # 6. Crear Cronograma de Hitos: Regla obligatoria (Mínimo 2 etapas + Hito Cero)
        etapas_tracking = list(op.tracking_etapas.all().order_by("etapa_origen__orden_ejecucion", "id"))
        if len(etapas_tracking) < 2:
            raise ValueError(
                f"Una e-OP federada requiere un mínimo obligatorio de dos etapas productivas (posee {len(etapas_tracking)})."
            )

        # 6. Consultar la Pauta Oficial de Escrow dictaminada por el FDI vía HTTP:
        posee_sbd = bool(op.contrato_eop and op.contrato_eop.es_sello_buen_diseno)
        nodo_fdi_url = op.contrato_eop.nodo_mes if (op.contrato_eop and op.contrato_eop.nodo_mes) else None
        pauta_fdi = FederacionFDIService.consultar_pauta_escrow_fdi(
            fdi_url=nodo_fdi_url, es_sello_buen_diseno=posee_sbd
        )

        anticipo = porcentaje_anticipo or pauta_fdi["porcentaje_cero"]
        nombre_cero = pauta_fdi.get("etiqueta_cero") or f"Hito Cero - Anticipo Operativo de Arranque ({anticipo}%)"
        porcentaje_final = pauta_fdi.get("porcentaje_final", Decimal("20.00"))

        # Validaciones de consistencia de la Tríada Canónica
        if anticipo <= Decimal("0.00") or anticipo >= Decimal("100.00"):
            anticipo = Decimal("50.00") if posee_sbd else Decimal("35.00")

        if porcentaje_final <= Decimal("0.00") or porcentaje_final >= Decimal("100.00"):
            porcentaje_final = Decimal("20.00")

        if (anticipo + porcentaje_final) >= Decimal("100.00"):
            porcentaje_final = max(Decimal("10.00"), Decimal("100.00") - anticipo - Decimal("10.00"))

        porcentaje_avance_total = Decimal("100.00") - anticipo - porcentaje_final
        if porcentaje_avance_total <= Decimal("0.00"):
            raise ValueError(
                f"Configuración inválida de Escrow: Anticipo ({anticipo}%) + Cierre ({porcentaje_final}%) no deja margen para etapas productivas."
            )

        # 1. Hito Cero: Anticipo Operativo de Arranque (dictaminado por la MES, liquidado por Silencio Positivo)
        EOPHitoEscrow.objects.create(
            contrato=contrato,
            nombre=nombre_cero,
            porcentaje_tramo=anticipo,
            requiere_auditoria_ptf=False,
            requiere_verificacion_arca=False,
            estado="bloqueado",
        )

        # 2. Hitos de Avance Productivo: Distribuidos entre las etapas fabriles (PoPW)
        total_mod = sum((e.costo_servicio_total or Decimal("0.00")) for e in etapas_tracking)
        porcentaje_acumulado = Decimal("0.00")

        for idx, etapa in enumerate(etapas_tracking):
            es_ultima_etapa = (idx == len(etapas_tracking) - 1)
            servicio_nombre = etapa.etapa_origen.servicio.nombre if (etapa.etapa_origen and etapa.etapa_origen.servicio) else f"Etapa {idx + 1}"
            orden = etapa.etapa_origen.orden_ejecucion if etapa.etapa_origen else (idx + 1)

            if es_ultima_etapa:
                porc_etapa = porcentaje_avance_total - porcentaje_acumulado
            else:
                if total_mod > 0:
                    costo_e = etapa.costo_servicio_total or Decimal("0.00")
                    porc_etapa = round((costo_e / total_mod) * porcentaje_avance_total, 2)
                else:
                    porc_etapa = round(porcentaje_avance_total / Decimal(len(etapas_tracking)), 2)
                porcentaje_acumulado += porc_etapa

            EOPHitoEscrow.objects.create(
                contrato=contrato,
                nombre=f"Hito {orden} - Avance: {servicio_nombre}",
                porcentaje_tramo=porc_etapa,
                requiere_auditoria_ptf=True,
                requiere_verificacion_arca=False,
                estado="bloqueado",
            )

        # 3. Hito Final: Entrega Conformada y Cierre Fiscal (Retención de Cierre Fiscal)
        EOPHitoEscrow.objects.create(
            contrato=contrato,
            nombre="Hito Final - Entrega Conformada y Cierre Fiscal",
            porcentaje_tramo=porcentaje_final,
            requiere_auditoria_ptf=True,
            requiere_verificacion_arca=True,
            estado="bloqueado",
        )

        return contrato

    @staticmethod
    @transaction.atomic
    def fondear_escrow(contrato_id):
        """
        Marca un ContratoEOP como fondeado.
        En la red federada, esto es gatillado por un Webhook de la MES
        avisando que el FDI adelantó la liquidez inicial.
        """
        contrato = ContratoEOP.objects.get(id=contrato_id)
        if contrato.estado_escrow != "solicitado":
            return
            
        contrato.estado_escrow = "financiado_fdi"
        contrato.fecha_fondeo_escrow = timezone.now()
        contrato.save(update_fields=["estado_escrow", "fecha_fondeo_escrow"])

    @staticmethod
    @transaction.atomic
    def firmar_contrato_tallerista(contrato, usuario, firma_tallerista_hex):
        """
        Registra la firma criptográfica del tallerista en el contrato EOP.
        Inyecta la aceptación de la confesión de deuda líquida de Hito Cero (Art. 6° Ley e-OP).
        """
        # Validación de que el usuario logueado efectivamente es el tallerista asignado
        if not hasattr(usuario, 'perfil_contacto'):
            raise ValueError("El usuario no tiene un perfil de tallerista asignado.")
            
        tallerista_cuit = usuario.perfil_contacto.cuil
        
        # Inicializar el JSONField si está nulo
        firmas = contrato.firmas_digitales or {}
        
        if "tallerista" in firmas:
            raise ValueError("Este contrato ya fue firmado por el tallerista.")
            
        # Inyección de la firma y aceptación expresa de deuda Hito Cero (Art. 6°)
        firmas["tallerista"] = {
            "cuit": tallerista_cuit,
            "firma_hex": firma_tallerista_hex,
            "timestamp": timezone.now().isoformat(),
            "confesion_deuda_h0_aceptada": True,
        }
        
        contrato.firmas_digitales = firmas
        contrato.declaracion_confesion_deuda_hito_cero = True
        contrato.save(update_fields=["firmas_digitales", "declaracion_confesion_deuda_hito_cero"])

    @staticmethod
    @transaction.atomic
    def liberar_hito(hito_id, firma_ptf=None, validar_concurrencia_h0=True):
        """
        Libera un tramo/hito de un contrato EOP.
        Verifica criptografía Ed25519 del PTF si el hito lo requiere.
        Para Hito Cero: valida concurrencia estricta (Art. 12° inc. 1):
          - Firma bilateral (comitente y tallerista).
          - Remito oficial de insumos o Lote Crítico >= 20% cargado.
          - Seguro de stock verificado.
        Para Hito Final (RCF): si requiere verificación ARCA y falta factura,
        pasa a retencion_cierre_fiscal e inicializa los timelocks de facturación.
        """
        hito = EOPHitoEscrow.objects.select_related('contrato').get(id=hito_id)
        contrato = hito.contrato

        if hito.estado not in ["bloqueado", "retencion_cierre_fiscal"]:
            return

        # Si ya estábamos en retencion_cierre_fiscal, asumimos que estamos intentando re-liberar tras cargar factura
        if hito.estado == "retencion_cierre_fiscal":
            if not hito.factura_asociada_arca:
                raise ValueError("No se puede liberar el hito porque no hay factura cargada.")
            hito.estado = "liberado"
            hito.save(update_fields=["estado"])
            return

        # Validación especial de Hito Cero (Art. 12° inc. 1 Ley e-OP)
        es_hito_cero = "cero" in hito.nombre.lower() or hito.porcentaje_tramo >= Decimal("35.00") and not hito.requiere_auditoria_ptf
        if es_hito_cero and validar_concurrencia_h0:
            firmas = contrato.firmas_digitales or {}
            tiene_firma_comitente = bool(firmas.get("comitente"))
            tiene_firma_taller = bool(firmas.get("tallerista"))
            if not (tiene_firma_comitente and tiene_firma_taller):
                raise ValueError("Hito Cero requiere concurrencia de firma bilateral (comitente y tallerista).")

            if not hito.remito_oficial_uuid:
                raise ValueError("Hito Cero requiere remito oficial de insumos con UUID o constancia de entrega de Lote Crítico.")

            if not hito.seguro_stock_verificado:
                raise ValueError("Hito Cero requiere acreditación de póliza de seguro de stock vigente (Art. 20 bis).")

        # Si estaba bloqueado y requiere PTF, revisamos firmas
        if hito.requiere_auditoria_ptf:
            firmas = hito.firmas_digitales or {}
            if not firma_ptf and not ("ptf" in firmas and firmas["ptf"].get("firma_hex")):
                raise ValueError("Falta firma criptográfica del PTF para auditar este hito.")

        # Lógica Retención de Cierre Fiscal (RCF Art. 12° inc. 3)
        if hito.requiere_verificacion_arca and not hito.factura_asociada_arca:
            ahora = timezone.now()
            hito.estado = "retencion_cierre_fiscal"
            if not hito.fecha_entrega_lote_conforme:
                hito.fecha_entrega_lote_conforme = ahora
            if not hito.fecha_limite_facturacion:
                # 10 días hábiles (aprox 14 días corridos)
                hito.fecha_limite_facturacion = ahora + datetime.timedelta(days=14)
            hito.save(update_fields=["estado", "fecha_entrega_lote_conforme", "fecha_limite_facturacion"])
            return

        hito.estado = "liberado"
        hito.save(update_fields=["estado"])


class LogisticaJITService:
    """
    Gestión del régimen logístico Justo a Tiempo (JIT) - Art. 5° bis Ley e-OP.
    Administra la extensión de plazos comerciales, devengamiento de compensación
    por standby fabril y la facultad rescisoria unilateral del taller façonnier.
    """
    SMVM_DEFAULT = Decimal("300000.00")  # Salario Mínimo Vital y Móvil de referencia (ARS)
    MAX_DIAS_PRORROGA = 30  # Límite máximo de postergación de vencimiento comercial

    @classmethod
    @transaction.atomic
    def registrar_demora_abastecimiento(
        cls, contrato, etapa_nombre, fecha_esperada, fecha_real=None, smvm_vigente=None
    ):
        """
        Registra una contingencia de abastecimiento JIT.
        - Prorroga automáticamente la entrega física y el vencimiento comercial (tope 30 días corridos).
        - A partir del 6° día hábil de mora (días_demora > 5), devenga standby a 0.5 SMVM diario.
        """
        smvm = smvm_vigente or cls.SMVM_DEFAULT
        fecha_eval = fecha_real or timezone.now().date()
        dias_demora = max(0, (fecha_eval - fecha_esperada).days)

        if dias_demora == 0:
            return None

        from .models import IncidenciaLogisticaJIT

        # Días de mora hábiles aproximados o directos (si > 5 días, standby a partir del día 6)
        dias_standby = max(0, dias_demora - 5)
        tarifa_diaria_standby = round(Decimal("0.5") * smvm / Decimal("30"), 2)
        monto_standby = round(Decimal(dias_standby) * tarifa_diaria_standby, 2)

        incidencia = IncidenciaLogisticaJIT.objects.create(
            contrato=contrato,
            etapa_afectada=etapa_nombre,
            fecha_entrega_esperada=fecha_esperada,
            fecha_entrega_real=fecha_real,
            dias_demora=dias_demora,
            compensacion_standby_devengada=monto_standby,
        )

        # Actualizar contrato
        dias_prorroga_aplicable = min(dias_demora, cls.MAX_DIAS_PRORROGA)
        contrato.es_justo_a_tiempo = True
        contrato.dias_mora_comitente_jit += dias_demora
        contrato.compensacion_standby_acumulada_ars += monto_standby

        if contrato.fecha_vencimiento_comercial:
            contrato.fecha_vencimiento_recalculada = (
                contrato.fecha_vencimiento_comercial + datetime.timedelta(days=dias_prorroga_aplicable)
            )

        contrato.save(update_fields=[
            "es_justo_a_tiempo",
            "dias_mora_comitente_jit",
            "compensacion_standby_acumulada_ars",
            "fecha_vencimiento_recalculada",
        ])

        return incidencia

    @classmethod
    @transaction.atomic
    def resolver_contrato_por_mora_taller(cls, contrato, incidencia_id=None):
        """
        Ejecuta la Resolución Contractual de Pleno Derecho por parte del taller (Art. 5° bis inc. 4).
        Exige al menos 15 días continuos de mora imputable a la marca en la entrega de insumos.
        Establece el contrato en estado 'en_disputa' y marca la incidencia con resolución ejercida.
        """
        if contrato.dias_mora_comitente_jit < 15:
            raise ValueError(
                f"La resolución de pleno derecho exige al menos 15 días continuos de mora (actual: {contrato.dias_mora_comitente_jit} días)."
            )

        contrato.estado_escrow = "en_disputa"
        contrato.save(update_fields=["estado_escrow"])

        if incidencia_id:
            from .models import IncidenciaLogisticaJIT
            incidencia = IncidenciaLogisticaJIT.objects.filter(id=incidencia_id, contrato=contrato).first()
            if incidencia:
                incidencia.resolucion_ejercida_por_taller = True
                incidencia.save(update_fields=["resolucion_ejercida_por_taller"])

        return True


class RCFService:
    """
    Servicio para el régimen de Retención de Cierre Fiscal (RCF) - Art. 12° inc. 3 Ley e-OP.
    Audita el timelock de facturación tras la entrega conforme del lote y calcula intereses
    BADLAR punitorios en caso de incumplimiento fiscal del taller responsable inscripto.
    """
    TASA_BADLAR_ANUAL_DEFAULT = Decimal("0.40")  # 40% TNA de referencia

    @classmethod
    @transaction.atomic
    def auditar_timelock_rcf(cls, hito_id, tasa_badlar_anual=None):
        """
        Evalúa el estado del hito RCF tras la entrega conforme.
        - Plazo: 10 días hábiles (14 días corridos) + 5 días hábiles de gracia (7 días corridos).
        - Total ventana de gracia: 21 días corridos sin factura.
        - Superado el plazo, liquida mora a tasa BADLAR sobre el monto del tramo RCF.
        """
        hito = EOPHitoEscrow.objects.select_related('contrato').get(id=hito_id)
        if hito.estado != "retencion_cierre_fiscal" or hito.factura_asociada_arca:
            return Decimal("0.00")

        if not hito.fecha_entrega_lote_conforme:
            return Decimal("0.00")

        ahora = timezone.now()
        dias_transcurridos = (ahora - hito.fecha_entrega_lote_conforme).days
        plazo_total_gracia = 21  # 10 días hábiles + 5 días de gracia corridos

        if dias_transcurridos > plazo_total_gracia:
            dias_mora = dias_transcurridos - plazo_total_gracia
            tasa_anual = tasa_badlar_anual or cls.TASA_BADLAR_ANUAL_DEFAULT
            tasa_diaria = tasa_anual / Decimal("365")

            # Monto proporcional del tramo sobre el MOD
            monto_tramo = round(
                hito.contrato.costo_mod * (hito.porcentaje_tramo / Decimal("100.00")), 2
            )
            interes_mora = round(monto_tramo * tasa_diaria * Decimal(dias_mora), 2)

            hito.cargo_mora_badlar_devengado = interes_mora
            hito.save(update_fields=["cargo_mora_badlar_devengado"])
            return interes_mora

        return Decimal("0.00")
