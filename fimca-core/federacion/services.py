import requests
from django.db import transaction
from django.conf import settings
from base.models import ConfiguracionNodo

class FederacionCreditoService:
    """
    Servicio utilitario cliente para consumir APIs del Nodo FDI / Red Federada.
    Nota: Las instancias ERP operan con FederacionFDIService en sus respectivos servicios.
    """
    @staticmethod
    def consultar_cupo_fdi():
        """
        Consulta en tiempo real el estado del crédito y la mora al servidor del FDI.
        """
        empresa = ConfiguracionNodo.objects.first()
        if not empresa:
            raise ValueError("No hay una ConfiguracionNodo definida en este nodo.")
        
        mi_cuit = empresa.cuit
        fdi_url = getattr(settings, 'NODO_FDI_URL', None)
        if not fdi_url:
            raise ValueError("NODO_FDI_URL no está configurado.")
        endpoint = f"{fdi_url.rstrip('/')}/fdi/api/v1/fdi/estado-credito/"
        
        try:
            respuesta = requests.get(
                endpoint,
                headers={"X-CUIT": mi_cuit},
                timeout=5
            )
            if respuesta.status_code == 200:
                return respuesta.json()
            elif respuesta.status_code == 404:
                raise ValueError("El FDI informa que la empresa no tiene una línea de crédito asignada.")
            else:
                raise ValueError(f"Error de red comunicándose con el FDI: {respuesta.status_code}")
        except requests.RequestException as e:
            raise ValueError(f"El Nodo FDI no está disponible: {str(e)}")

    consultar_cupo_mes = consultar_cupo_fdi

    @staticmethod
    def consultar_pauta_escrow_fdi(nodo_fdi_url=None, es_sello_buen_diseno=False):
        """
        Consulta por HTTP la pauta oficial de porcentajes de Escrow
        vigente (Hito Cero, Sello Buen Diseño, Hito Final).
        """
        base_url = (nodo_fdi_url or getattr(settings, 'NODO_FDI_URL', None))
        if not base_url:
            raise ValueError("NODO_FDI_URL no está configurado.")
        endpoint = f"{base_url.rstrip('/')}/federacion/api/v1/escrow/pauta/"
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
                    "nombre_pauta": data.get("nombre_pauta", "Pauta Oficial Escrow FDI"),
                }
        except Exception:
            pass

        # Fallback de contingencia local si el FDI no responde
        from decimal import Decimal
        porc_cero = Decimal("50.00") if es_sello_buen_diseno else Decimal("35.00")
        porc_final = Decimal("20.00")
        return {
            "porcentaje_cero": porc_cero,
            "etiqueta_cero": f"Hito Cero - Anticipo Operativo de Arranque ({'Sello Buen Diseño 50%' if es_sello_buen_diseno else 'Estándar 35%'})",
            "porcentaje_final": porc_final,
            "porcentaje_avance": Decimal("100.00") - porc_cero - porc_final,
            "nombre_pauta": "Pauta Oficial Escrow FDI (Fallback Local)",
        }

    consultar_pauta_escrow_mes = consultar_pauta_escrow_fdi

    @staticmethod
    def transmitir_eop_al_fdi(contrato_eop, firma_comitente_hex, clave_publica_hex, nodo_fdi_url=None):
        """
        Emite el HTTP POST con el payload canónico firmado hacia el endpoint receptor
        (/federacion/eop/entrante/).
        """
        import json
        from decimal import Decimal

        empresa = ConfiguracionNodo.objects.first()
        if not empresa:
            raise ValueError("No hay una ConfiguracionNodo definida en este nodo.")

        base_url = (nodo_fdi_url or getattr(settings, 'NODO_FDI_URL', None))
        if not base_url:
            raise ValueError("NODO_FDI_URL no está configurado.")
        endpoint = f"{base_url.rstrip('/')}/federacion/eop/entrante/"

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
                    f"Error rechazado por el FDI ({respuesta.status_code}): {respuesta.text}"
                )
        except requests.RequestException as e:
            raise ValueError(f"Fallo de conexión al despachar e-OP al Nodo FDI: {str(e)}")

    transmitir_eop_a_mes = transmitir_eop_al_fdi



