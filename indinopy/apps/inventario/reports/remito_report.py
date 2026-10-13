from typing import Any, Dict
from apps.base.reports.base import BasePDFReport
from apps.base.models import ConfiguracionEmpresa


class RemitoPDFReport(BasePDFReport):
    """
    Generador de Remito Oficial en PDF para despachos y movimientos logísticos.
    Soporta:
    1. Remito de Entrega / Despacho a Clientes (Ventas).
    2. Remito de Traslado a Producción / Talleres Externos (con Cláusula de Custodia Inembargable CCCN).
    3. Remito de Traslado Interno entre depósitos.
    """

    template_name = "inventario/reports/remito_pdf.html"

    @property
    def nombre_archivo(self) -> str:
        return f"Remito_{self.objeto.numero}.pdf"

    def get_context_data(self) -> Dict[str, Any]:
        remito = self.objeto
        config = ConfiguracionEmpresa.get_solo()

        # Detectar si es un traslado a producción / taller o fasón
        es_traslado_produccion = False
        if remito.tipo == "traslado" and getattr(remito.ubicacion_destino, "tipo", "") in ["fason", "produccion"]:
            es_traslado_produccion = True
        elif remito.numero and remito.numero.startswith("TRA-"):
            es_traslado_produccion = True

        return {
            "remito": remito,
            "empresa": config,
            "destinatario": remito.contacto,
            "origen": remito.ubicacion_origen,
            "destino": remito.ubicacion_destino,
            "lineas": remito.lineas.select_related("producto", "producto__template", "producto__template__unidad_medida").all(),
            "es_traslado_produccion": es_traslado_produccion,
            "clausula_inembargabilidad": es_traslado_produccion,
            "es_fiscal": remito.es_fiscal,
        }
