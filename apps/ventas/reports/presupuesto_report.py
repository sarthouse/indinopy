from typing import Any, Dict
from apps.base.reports.base import BasePDFReport
from apps.base.models import ConfiguracionEmpresa


class PresupuestoPDFReport(BasePDFReport):
    """
    Generador de Presupuesto / Cotización Comercial y Nota de Pedido en PDF.
    Dependiendo del estado ('presupuesto' vs 'nota_pedido' / 'confirmado'), adapta
    el título formal del documento, las cláusulas de validez y la identificación del cliente.
    """

    template_name = "ventas/reports/presupuesto_pdf.html"

    @property
    def nombre_archivo(self) -> str:
        prefijo = "Presupuesto" if self.objeto.estado == "presupuesto" else "Nota_Pedido"
        return f"{prefijo}_{self.objeto.numero}.pdf"

    def get_context_data(self) -> Dict[str, Any]:
        orden = self.objeto
        config = ConfiguracionEmpresa.get_solo()

        es_presupuesto = orden.estado == "presupuesto"

        return {
            "orden": orden,
            "empresa": config,
            "cliente": orden.cliente,
            "lineas": orden.lineas.select_related("producto", "producto__template").all(),
            "recargos": orden.recargos.all(),
            "es_presupuesto": es_presupuesto,
            "titulo_documento": "PRESUPUESTO / COTIZACIÓN" if es_presupuesto else "NOTA DE PEDIDO",
        }
