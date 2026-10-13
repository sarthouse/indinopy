import requests
from django.db import transaction
from django.conf import settings
from base.models import ConfiguracionEmpresa

class FederacionCreditoService:
    """
    Servicio cliente para consumir las APIs del Nodo Central (MES).
    """
    
    @staticmethod
    def consultar_cupo_mes():
        """
        Consulta en tiempo real (Pull) el estado del crédito y la mora
        al servidor de la MES.
        """
        empresa = ConfiguracionEmpresa.objects.first()
        if not empresa:
            raise ValueError("No hay una ConfiguracionEmpresa definida en este nodo.")
        
        mi_cuit = empresa.cuit
        
        # En producción, esta URL vendría de settings. NODO_MES_URL
        mes_url = getattr(settings, 'NODO_MES_URL', 'http://localhost:8000')
        endpoint = f"{mes_url}/mes/api/v1/fdi/estado-credito/"
        
        try:
            # Petición HTTP al nodo MES. Se inyecta el CUIT propio en los headers
            respuesta = requests.get(
                endpoint,
                headers={"X-CUIT": mi_cuit},
                timeout=5
            )
            
            if respuesta.status_code == 200:
                return respuesta.json()
            elif respuesta.status_code == 404:
                raise ValueError("La MES informa que tu empresa no tiene una línea de crédito asignada.")
            else:
                raise ValueError(f"Error de red comunicándose con la MES: {respuesta.status_code}")
                
        except requests.RequestException as e:
            raise ValueError(f"El Nodo MES no está disponible: {str(e)}")

    @staticmethod
    def consultar_pauta_escrow_mes(nodo_mes_url=None, es_sello_buen_diseno=False):
        """
        Consulta por HTTP a la API de la MES la pauta oficial de porcentajes de Escrow
        vigente (Hito Cero, Sello Buen Diseño, Hito Final).
        """
        base_url = (nodo_mes_url or getattr(settings, 'NODO_MES_URL', 'http://localhost:8000')).rstrip('/')
        endpoint = f"{base_url}/federacion/api/v1/escrow/pauta/"
        params = {"sello_buen_diseno": "true" if es_sello_buen_diseno else "false"}

        try:
            resp = requests.get(endpoint, params=params, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                from decimal import Decimal
                return {
                    "porcentaje_cero": Decimal(str(data["porcentaje_cero"])),
                    "etiqueta_cero": data["etiqueta_cero"],
                    "porcentaje_final": Decimal(str(data["porcentaje_final"])),
                    "porcentaje_avance": Decimal(str(data["porcentaje_avance"])),
                    "nombre_pauta": data.get("nombre_pauta", "Pauta Oficial Escrow MES"),
                }
        except Exception:
            pass

        # Fallback de contingencia local si la MES no responde
        from decimal import Decimal
        porc_cero = Decimal("50.00") if es_sello_buen_diseno else Decimal("35.00")
        porc_final = Decimal("20.00")
        return {
            "porcentaje_cero": porc_cero,
            "etiqueta_cero": f"Hito Cero - Anticipo Operativo de Arranque ({'Sello Buen Diseño 50%' if es_sello_buen_diseno else 'Estándar 35%'})",
            "porcentaje_final": porc_final,
            "porcentaje_avance": Decimal("100.00") - porc_cero - porc_final,
            "nombre_pauta": "Pauta Oficial Escrow MES (Fallback Local)",
        }

    @staticmethod
    def transmitir_eop_a_mes(contrato_eop, firma_comitente_hex, clave_publica_hex):
        """
        Emite el HTTP POST con el payload canónico firmado hacia el endpoint de la MES
        (/federacion/eop/entrante/).
        """
        import json
        from decimal import Decimal

        empresa = ConfiguracionEmpresa.objects.first()
        if not empresa:
            raise ValueError("No hay una ConfiguracionEmpresa definida en este nodo.")

        mes_url = getattr(settings, 'NODO_MES_URL', 'http://localhost:8000').rstrip('/')
        endpoint = f"{mes_url}/federacion/eop/entrante/"

        # Aseguramos el hash de seguridad
        contrato_eop.sellar_hash_seguridad()

        # Validación Inviolable: La e-OP no puede transmitirse a la red federada sin la firma del tallerista gestor
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
                    f"Error rechazado por la MES ({respuesta.status_code}): {respuesta.text}"
                )
        except requests.RequestException as e:
            raise ValueError(f"Fallo de conexión al despachar e-OP al Nodo MES: {str(e)}")



