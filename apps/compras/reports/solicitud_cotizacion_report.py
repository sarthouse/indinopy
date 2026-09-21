from typing import Any, Dict
from apps.base.reports.base import BasePDFReport
from apps.base.models import ConfiguracionEmpresa


class SolicitudCotizacionPDFReport(BasePDFReport):
    """
    Generador de Solicitud de Cotización / Presupuesto (RFQ) en PDF para proveedores.
    A diferencia de la Orden de Compra formal, no compromete la compra ni exhibe necesariamente
    precios cerrados, solicitando formalmente cotización de precios, plazo de entrega y validez.
    """

    template_name = "compras/reports/solicitud_cotizacion_pdf.html"

    @property
    def nombre_archivo(self) -> str:
        return f"Solicitud_Cotizacion_{self.objeto.numero}.pdf"

    def get_context_data(self) -> Dict[str, Any]:
        oc = self.objeto
        config = ConfiguracionEmpresa.get_solo()

        return {
            "oc": oc,
            "empresa": config,
            "proveedor": oc.proveedor,
            "lineas": oc.lineas.select_related("producto", "unidad_medida").all(),
            "moneda": oc.moneda,
        }
