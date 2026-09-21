from typing import Any, Dict
from apps.base.reports.base import BasePDFReport
from apps.base.models import ConfiguracionEmpresa


class OrdenCompraPDFReport(BasePDFReport):
    """
    Generador de Orden de Compra Oficial en PDF para envío a proveedores.
    Incluye membrete institucional, datos fiscales del proveedor, condiciones de entrega/pago
    y detalle valorizado con desglose de IVA y totales.
    """

    template_name = "compras/reports/orden_compra_pdf.html"

    @property
    def nombre_archivo(self) -> str:
        return f"Orden_Compra_{self.objeto.numero}.pdf"

    def get_context_data(self) -> Dict[str, Any]:
        oc = self.objeto
        config = ConfiguracionEmpresa.get_solo()

        return {
            "oc": oc,
            "empresa": config,
            "proveedor": oc.proveedor,
            "lineas": oc.lineas.select_related("producto", "unidad_medida", "impuesto").all(),
            "moneda": oc.moneda,
        }
