from decimal import Decimal
from typing import Any, List, Optional
from apps.base.reports.base import BaseTabularReport
from apps.inventario.models import StockQuant


class InventarioStockExcelReport(BaseTabularReport):
    """
    Reporte tabular de existencias e inventario físico valuado.
    Permite auditar en tiempo real:
    - Cantidad física en mano por almacén y lote.
    - Cantidad reservada (comprometida en ventas u órdenes de producción).
    - Cantidad disponible neta para despacho.
    - Costo unitario y valuación total del activo de inventario.
    """

    extension = "xlsx"

    def __init__(
        self,
        ubicacion_id: Optional[int] = None,
        tipo_ubicacion: Optional[str] = None,
        categoria_id: Optional[int] = None,
        tipo_producto: Optional[str] = None,
        solo_con_stock: bool = True,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.ubicacion_id = ubicacion_id
        self.tipo_ubicacion = tipo_ubicacion
        self.categoria_id = categoria_id
        self.tipo_producto = tipo_producto
        self.solo_con_stock = solo_con_stock

    @property
    def nombre_archivo(self) -> str:
        return "Inventario_Stock_Valuado"

    def get_queryset(self):
        qs = StockQuant.objects.select_related(
            "producto",
            "producto__template",
            "producto__template__categoria",
            "producto__template__unidad_medida",
            "ubicacion",
            "lote",
        )

        if self.solo_con_stock:
            qs = qs.filter(cantidad_fisica__gt=Decimal("0.0"))

        if self.ubicacion_id:
            qs = qs.filter(ubicacion_id=self.ubicacion_id)

        if self.tipo_ubicacion:
            qs = qs.filter(ubicacion__tipo=self.tipo_ubicacion)

        if self.categoria_id:
            qs = qs.filter(producto__template__categoria_id=self.categoria_id)

        if self.tipo_producto:
            qs = qs.filter(producto__template__tipo_producto=self.tipo_producto)

        return qs.order_by("ubicacion__nombre", "producto__template__nombre", "producto__sku")

    def get_headers(self) -> List[str]:
        return [
            "Almacén / Ubicación",
            "Tipo de Almacén",
            "Categoría",
            "SKU",
            "Descripción / Variante",
            "Lote",
            "U.M.",
            "Stock Físico",
            "Stock Reservado",
            "Stock Disponible",
            "Costo Unitario ($)",
            "Valuación Total ($)",
        ]

    def get_rows(self) -> List[List[Any]]:
        rows = []
        total_fisico = Decimal("0.0")
        total_reservado = Decimal("0.0")
        total_disponible = Decimal("0.0")
        total_valuacion = Decimal("0.00")

        for quant in self.get_queryset():
            prod = quant.producto
            template = prod.template
            uom = template.unidad_medida.simbolo if template.unidad_medida else "u"
            costo = template.costo or Decimal("0.00")
            valuacion = quant.cantidad_fisica * costo

            fisico = quant.cantidad_fisica
            reservado = quant.cantidad_reservada
            disponible = quant.cantidad_disponible

            total_fisico += fisico
            total_reservado += reservado
            total_disponible += disponible
            total_valuacion += valuacion

            rows.append([
                quant.ubicacion.nombre,
                quant.ubicacion.get_tipo_display(),
                template.categoria.nombre if template.categoria else "General",
                prod.sku,
                str(prod),
                quant.lote.numero if quant.lote else "Sin Lote",
                uom,
                float(fisico),
                float(reservado),
                float(disponible),
                float(costo),
                float(valuacion),
            ])

        # Fila de Totales Generales
        rows.append([
            "TOTAL GENERAL",
            "-",
            "-",
            "-",
            "-",
            "-",
            "-",
            float(total_fisico),
            float(total_reservado),
            float(total_disponible),
            "-",
            float(total_valuacion),
        ])

        return rows
