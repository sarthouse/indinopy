from decimal import Decimal
from typing import Any, Dict
from apps.base.reports.base import BasePDFReport
from apps.mes.models import EdicionBoletinSectorial


class BoletinSectorialPDFReport(BasePDFReport):
    """
    Reporte oficial en formato PDF del Boletín Oficial Sectorial de la MES.
    Publica acuerdos paritarios, Tarifario Homologado de Convenio en UCI y resoluciones colegiadas.
    """

    template_name = "mes/reports/boletin_report.html"
    nombre_archivo = "boletin_oficial_mes"

    def __init__(self, boletin: EdicionBoletinSectorial, **kwargs):
        super().__init__(objeto_origen=boletin, **kwargs)
        self.boletin = boletin
        self.nombre_archivo = f"boletin_mes_edicion_{boletin.numero_edicion}"

    def get_context_data(self) -> Dict[str, Any]:
        sumario = self.boletin.sumario_resoluciones or {}
        tarifas = sumario.get("tarifas_vigentes_uci", [])
        talleres_sbd = sumario.get("talleres_sello_buen_diseno", [])
        laudos = sumario.get("laudos_arbitrales_recientes", [])

        return {
            "boletin": self.boletin,
            "comision": self.boletin.comision,
            "tarifas": tarifas,
            "talleres_sbd": talleres_sbd,
            "laudos": laudos,
            "hash_seguridad": self.boletin.hash_seguridad_publicacion,
            "firma_mes": self.boletin.firma_mes,
            "fecha_emision": self.boletin.fecha_publicacion.strftime("%d/%m/%Y"),
        }
