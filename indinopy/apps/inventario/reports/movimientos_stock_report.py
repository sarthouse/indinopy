from datetime import date
from decimal import Decimal
from typing import Any, List, Optional
from apps.base.reports.base import BaseTabularReport
from apps.inventario.models import LineaMovimientoStock


class MovimientosStockExcelReport(BaseTabularReport):
    """
    Reporte tabular de trazabilidad cronológica de movimientos de inventario (Kardex General).
    Registra cada línea de remito de recepción, entrega o traslado interno:
    - Fecha y hora del movimiento.
    - N° de Remito físico o fiscal.
    - Documento generador (Orden de Venta, Orden de Compra, Orden de Producción).
    - Contacto involucrado (Proveedor, Cliente o Tallerista).
    - Depósitos de origen y destino por partida doble.
    - SKU, lote, cantidad y estado de ejecución.
    """

    extension = "xlsx"

    def __init__(
        self,
        fecha_desde: Optional[date] = None,
        fecha_hasta: Optional[date] = None,
        tipo_movimiento: Optional[str] = None,
        producto_id: Optional[int] = None,
        ubicacion_id: Optional[int] = None,
        estado: Optional[str] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.fecha_desde = fecha_desde
        self.fecha_hasta = fecha_hasta
        self.tipo_movimiento = tipo_movimiento
        self.producto_id = producto_id
        self.ubicacion_id = ubicacion_id
        self.estado = estado

    @property
    def nombre_archivo(self) -> str:
        desde_str = self.fecha_desde.strftime("%Y%m%d") if self.fecha_desde else "inicio"
        hasta_str = self.fecha_hasta.strftime("%Y%m%d") if self.fecha_hasta else "actual"
        return f"Movimientos_Stock_{desde_str}_{hasta_str}"

    def get_queryset(self):
        qs = LineaMovimientoStock.objects.select_related(
            "movimiento",
            "movimiento__contacto",
            "producto",
            "producto__template",
            "producto__template__unidad_medida",
            "ubicacion_origen",
            "ubicacion_destino",
            "lote",
        )

        if self.fecha_desde:
            qs = qs.filter(movimiento__fecha__gte=self.fecha_desde)

        if self.fecha_hasta:
            qs = qs.filter(movimiento__fecha__lte=self.fecha_hasta)

        if self.tipo_movimiento:
            qs = qs.filter(movimiento__tipo=self.tipo_movimiento)

        if self.producto_id:
            qs = qs.filter(producto_id=self.producto_id)

        if self.ubicacion_id:
            from django.db.models import Q
            qs = qs.filter(Q(ubicacion_origen_id=self.ubicacion_id) | Q(ubicacion_destino_id=self.ubicacion_id))

        if self.estado:
            qs = qs.filter(estado=self.estado)

        return qs.order_by("-movimiento__fecha", "-movimiento__id", "id")

    def get_headers(self) -> List[str]:
        return [
            "Fecha",
            "N° Remito / Movimiento",
            "Tipo Operación",
            "Tipo Comprobante",
            "Doc. Generador",
            "Contacto (Taller / Prov / Cliente)",
            "Depósito Origen",
            "Depósito Destino",
            "SKU",
            "Producto / Variante",
            "Lote",
            "U.M.",
            "Cantidad Solicitada",
            "Cantidad Realizada",
            "Estado Línea",
        ]

    def get_rows(self) -> List[List[Any]]:
        rows = []
        total_solicitada = Decimal("0.0")
        total_realizada = Decimal("0.0")

        for linea in self.get_queryset():
            mov = linea.movimiento
            prod = linea.producto
            template = prod.template
            uom = template.unidad_medida.simbolo if template.unidad_medida else "u"

            total_solicitada += linea.cantidad
            total_realizada += linea.cantidad_hecha

            doc_gen = str(mov.documento_origen_obj or mov.documento_origen or "-")
            contacto_str = mov.contacto.nombre if mov.contacto else "-"

            rows.append([
                mov.fecha.strftime("%d/%m/%Y") if mov.fecha else "-",
                mov.numero,
                mov.get_tipo_display(),
                "Fiscal (R)" if mov.es_fiscal else "Interno (X)",
                doc_gen,
                contacto_str,
                linea.ubicacion_origen.nombre,
                linea.ubicacion_destino.nombre,
                prod.sku,
                str(prod),
                linea.lote.numero if linea.lote else "Sin Lote",
                uom,
                float(linea.cantidad),
                float(linea.cantidad_hecha),
                linea.get_estado_display(),
            ])

        # Fila de Totales
        rows.append([
            "TOTAL GENERAL",
            "-",
            "-",
            "-",
            "-",
            "-",
            "-",
            "-",
            "-",
            "-",
            "-",
            "-",
            float(total_solicitada),
            float(total_realizada),
            "-",
        ])

        return rows
