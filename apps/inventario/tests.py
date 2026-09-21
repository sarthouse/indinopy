from decimal import Decimal
from django.test import TestCase
from django.utils import timezone

from apps.inventario.models import (
    Ubicacion,
    Producto,
    ProductoTemplate,
    UnidadMedida,
    StockQuant,
    MovimientoStock,
    LineaMovimientoStock,
)
from apps.inventario.reports.inventario_stock_report import InventarioStockExcelReport
from apps.inventario.reports.movimientos_stock_report import MovimientosStockExcelReport


class InventarioReportesTestCase(TestCase):
    def setUp(self):
        self.uom, _ = UnidadMedida.objects.get_or_create(
            nombre="Pares", defaults={"simbolo": "par", "tipo": "unidad"}
        )
        self.template = ProductoTemplate.objects.create(
            nombre="Bota Táctica Cuero",
            precio=Decimal("60000.00"),
            costo=Decimal("35000.00"),
            unidad_medida=self.uom,
        )
        self.producto = Producto.objects.create(template=self.template, sku="BOTA-TAC-42")

        self.almacen = Ubicacion.objects.create(nombre="Depósito Central Test", tipo="interna")
        self.ubicacion_cliente, _ = Ubicacion.objects.get_or_create(
            tipo="cliente", nombre="Cliente Virtual"
        )

    def test_inventario_stock_excel_report(self):
        """
        Valida que InventarioStockExcelReport calcule con precisión:
        - Stock físico en mano.
        - Stock reservado.
        - Stock neto disponible (Físico - Reservado).
        - Valuación total económica (Físico × Costo Unitario).
        """
        StockQuant.objects.create(
            producto=self.producto,
            ubicacion=self.almacen,
            cantidad_fisica=Decimal("50.0"),
            cantidad_reservada=Decimal("10.0"),
        )

        reporte = InventarioStockExcelReport(ubicacion_id=self.almacen.id)
        headers = reporte.get_headers()
        rows = reporte.get_rows()

        self.assertIn("Stock Físico", headers)
        self.assertIn("Stock Reservado", headers)
        self.assertIn("Stock Disponible", headers)
        self.assertIn("Valuación Total ($)", headers)

        # 1 fila de producto + 1 fila de total general
        self.assertEqual(len(rows), 2)

        row_prod = rows[0]
        self.assertEqual(row_prod[3], "BOTA-TAC-42")
        self.assertEqual(row_prod[7], 50.0)         # Físico
        self.assertEqual(row_prod[8], 10.0)         # Reservado
        self.assertEqual(row_prod[9], 40.0)         # Disponible
        self.assertEqual(row_prod[10], 35000.0)     # Costo Unitario
        self.assertEqual(row_prod[11], 1750000.0)   # Valuación (50 * $35,000)

        # Fila de Totales
        row_total = rows[1]
        self.assertEqual(row_total[0], "TOTAL GENERAL")
        self.assertEqual(row_total[7], 50.0)
        self.assertEqual(row_total[8], 10.0)
        self.assertEqual(row_total[9], 40.0)
        self.assertEqual(row_total[11], 1750000.0)

        # Validar generación binaria (Excel / CSV)
        binario = reporte.render()
        self.assertGreater(len(binario), 0)

    def test_movimientos_stock_excel_report(self):
        """
        Valida que MovimientosStockExcelReport genere la trazabilidad cronológica
        (Kardex) de remitos por partida doble.
        """
        remito = MovimientoStock.objects.create(
            numero="REM-TEST-001",
            tipo="entrega",
            ubicacion_origen=self.almacen,
            ubicacion_destino=self.ubicacion_cliente,
            fecha=timezone.now().date(),
            estado="realizado",
        )
        LineaMovimientoStock.objects.create(
            movimiento=remito,
            producto=self.producto,
            cantidad=Decimal("12.0"),
            cantidad_hecha=Decimal("12.0"),
            ubicacion_origen=self.almacen,
            ubicacion_destino=self.ubicacion_cliente,
            estado="realizado",
        )

        reporte = MovimientosStockExcelReport(producto_id=self.producto.id)
        headers = reporte.get_headers()
        rows = reporte.get_rows()

        self.assertIn("N° Remito / Movimiento", headers)
        self.assertIn("Cantidad Realizada", headers)

        # 1 fila de movimiento + 1 fila de total general
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][1], "REM-TEST-001")
        self.assertEqual(rows[0][8], "BOTA-TAC-42")
        self.assertEqual(rows[0][12], 12.0)
        self.assertEqual(rows[0][13], 12.0)

        binario = reporte.render()
        self.assertGreater(len(binario), 0)
