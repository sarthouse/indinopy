from datetime import date
from decimal import Decimal
from typing import Any, List, Optional
from django.db.models import F
from apps.base.reports.base import BaseTabularReport
from apps.compras.models import LineaOrdenCompra


class RecepcionesPendientesExcelReport(BaseTabularReport):
    """
    Reporte tabular de Abastecimiento y Control de Entregas (Backorders de Compras).
    Lista todos los insumos y productos comprometidos en Órdenes de Compra confirmadas
    que aún no ingresaron en su totalidad al almacén físico.
    """

    extension = "xlsx"

    def __init__(
        self,
        proveedor_id: Optional[int] = None,
        fecha_desde: Optional[date] = None,
        fecha_hasta: Optional[date] = None,
        solo_vencidas: bool = False,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.proveedor_id = proveedor_id
        self.fecha_desde = fecha_desde
        self.fecha_hasta = fecha_hasta
        self.solo_vencidas = solo_vencidas

    @property
    def nombre_archivo(self) -> str:
        hoy_str = date.today().strftime("%Y%m%d")
        return f"Recepciones_Pendientes_Compras_{hoy_str}"

    def get_queryset(self):
        qs = LineaOrdenCompra.objects.select_related(
            "orden_compra",
            "orden_compra__proveedor",
            "orden_compra__moneda",
            "producto",
            "producto__template",
            "unidad_medida",
        ).filter(
            orden_compra__estado__in=["confirmado"],
            cantidad__gt=F("cantidad_recibida"),
        )

        if self.proveedor_id:
            qs = qs.filter(orden_compra__proveedor_id=self.proveedor_id)

        if self.fecha_desde:
            qs = qs.filter(orden_compra__fecha__gte=self.fecha_desde)

        if self.fecha_hasta:
            qs = qs.filter(orden_compra__fecha__lte=self.fecha_hasta)

        if self.solo_vencidas:
            qs = qs.filter(orden_compra__fecha_entrega_esperada__lt=date.today())

        return qs.order_by("orden_compra__fecha_entrega_esperada", "orden_compra__numero")

    def get_headers(self) -> List[str]:
        return [
            "N° Orden Compra",
            "Fecha Emisión",
            "Fecha Entrega Esperada",
            "Estado Entrega",
            "Proveedor",
            "CUIT",
            "SKU Insumo",
            "Descripción",
            "U.M.",
            "Cant. Pedida",
            "Cant. Recibida",
            "Cant. Pendiente",
            "Moneda",
            "Precio Unit.",
            "Importe Pendiente",
            "OP Origen",
        ]

    def get_row_data(self, item: Any) -> List[Any]:
        linea: LineaOrdenCompra = item
        oc = linea.orden_compra
        hoy = date.today()

        # Determinar atraso
        if oc.fecha_entrega_esperada:
            if oc.fecha_entrega_esperada < hoy:
                dias_atraso = (hoy - oc.fecha_entrega_esperada).days
                estado_entrega = f"Demorado ({dias_atraso} d)"
            elif oc.fecha_entrega_esperada == hoy:
                estado_entrega = "Vence Hoy"
            else:
                dias_restantes = (oc.fecha_entrega_esperada - hoy).days
                estado_entrega = f"En plazo ({dias_restantes} d)"
        else:
            estado_entrega = "Sin fecha límite"

        importe_pendiente = (linea.cantidad_pendiente * linea.precio_unitario).quantize(Decimal("0.01"))

        return [
            oc.numero,
            oc.fecha.strftime("%d/%m/%Y") if oc.fecha else "",
            oc.fecha_entrega_esperada.strftime("%d/%m/%Y") if oc.fecha_entrega_esperada else "-",
            estado_entrega,
            oc.proveedor.nombre if oc.proveedor else "",
            oc.proveedor.cuil or oc.proveedor.cuit or "",
            linea.producto.sku,
            linea.descripcion or (linea.producto.template.nombre if linea.producto.template else linea.producto.sku),
            linea.unidad_medida.codigo if linea.unidad_medida else "UN",
            float(linea.cantidad),
            float(linea.cantidad_recibida),
            float(linea.cantidad_pendiente),
            oc.moneda.simbolo if oc.moneda else "$",
            float(linea.precio_unitario),
            float(importe_pendiente),
            oc.origen_op.codigo if oc.origen_op else "-",
        ]
