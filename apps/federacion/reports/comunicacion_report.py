from typing import Any, Dict, Optional
from apps.base.reports.base import BasePDFReport
from apps.federacion.models import ComunicacionOficialFederada, CedulaDestinatario


class ComunicacionOficialPDFReport(BasePDFReport):
    """
    Reporte oficial en formato PDF de la Cédula de Notificación Electrónica / Nota Oficial.
    Renderiza de forma adaptativa según el observador:
    - Si es el Emisor: Muestra el tablero completo de acuses y todos los destinatarios (TO, CC, CCO).
    - Si es Destinatario Principal (TO) o Copia (CC): Solo muestra las partes públicas (TO y CC).
    - Si es Destinatario Oculto (CCO): Muestra partes públicas y destaca su carácter confidencial individual.
    """

    template_name = "federacion/reports/cedula_notificacion.html"
    nombre_archivo = "cedula_notificacion_oficial"

    def __init__(self, comunicacion: ComunicacionOficialFederada, cuit_observador: Optional[str] = None, **kwargs):
        super().__init__(objeto_origen=comunicacion, **kwargs)
        self.comunicacion = comunicacion
        self.cuit_observador = cuit_observador
        num = (comunicacion.numero_oficial or str(comunicacion.uuid_identificador)[:8]).replace("/", "_")
        self.nombre_archivo = f"cedula_{num}"

    def get_context_data(self) -> Dict[str, Any]:
        com = self.comunicacion
        todos_destinatarios = list(com.destinatarios.select_related("nodo_destino").all())

        es_emisor = (self.cuit_observador == com.cuit_emisor) or (self.cuit_observador is None)

        # Destinatarios principales (TO) y copias públicas (CC)
        destinatarios_principales = [d for d in todos_destinatarios if d.modo_recepcion == "principal"]
        destinatarios_cc = [d for d in todos_destinatarios if d.modo_recepcion == "copia_publica"]
        destinatarios_cco = [d for d in todos_destinatarios if d.modo_recepcion == "copia_oculta"]

        es_observador_cco = False
        mi_cedula_cco = None

        if not es_emisor and self.cuit_observador:
            for d in destinatarios_cco:
                if d.cuit_destino == self.cuit_observador:
                    es_observador_cco = True
                    mi_cedula_cco = d
                    break

        return {
            "comunicacion": com,
            "es_emisor": es_emisor,
            "es_observador_cco": es_observador_cco,
            "mi_cedula_cco": mi_cedula_cco,
            "destinatarios_principales": destinatarios_principales,
            "destinatarios_cc": destinatarios_cc,
            "destinatarios_cco": destinatarios_cco if es_emisor else [],
            "todos_destinatarios": todos_destinatarios,
            "fecha_emision_formateada": com.fecha_emision.strftime("%d/%m/%Y %H:%M") if com.fecha_emision else "BORRADOR",
        }
