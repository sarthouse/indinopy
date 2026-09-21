from decimal import Decimal
from datetime import date
from django.test import TestCase

from apps.base.models import Moneda
from apps.contactos.models import Contacto
from apps.inventario.models import ProductoTemplate, Producto, Categoria, UnidadMedida, Ubicacion, StockQuant, MovimientoStock
from apps.contabilidad.models import CondicionPago, Impuesto, Diario, DocumentoDeuda
from apps.compras.models import OrdenCompra, LineaOrdenCompra, TarifaProveedor
from apps.compras.services import ComprasService
from apps.compras.reports.orden_compra_report import OrdenCompraPDFReport


class ComprasFlowTestCase(TestCase):
    def setUp(self):
        self.moneda = Moneda.objects.create(codigo="ARS", nombre="Pesos Argentinos", simbolo="$")
        self.cond_pago = CondicionPago.objects.create(nombre="Cuenta Corriente 30 días")

        self.proveedor = Contacto.objects.create(
            nombre="Distribuidora Textil S.A.",
            tipo="proveedor",
            cuil="30-71234567-9",
            condicion_iva="RI",
            direccion="Av. Corrientes 1234, CABA",
        )

        self.um = UnidadMedida.objects.create(nombre="Metros", codigo="MTR")
        self.cat = Categoria.objects.create(nombre="Materia Prima")
        self.template = ProductoTemplate.objects.create(
            nombre="Tela Gabardina 8oz",
            tipo="almacenable",
            categoria=self.cat,
            unidad_medida=self.um,
        )
        self.producto = Producto.objects.create(
            template=self.template,
            sku="INS-GAB-001",
        )

        self.iva21 = Impuesto.objects.create(
            nombre="IVA 21%",
            tipo="iva",
            alicuota=Decimal("21.00"),
            afip_id=5,
        )

        self.almacen_interno = Ubicacion.objects.create(
            nombre="Almacén Central",
            tipo="interna",
            activa=True,
        )
        self.ubicacion_prov = Ubicacion.objects.create(
            nombre="Proveedores",
            tipo="proveedor",
            activa=True,
        )

        self.tarifa = TarifaProveedor.objects.create(
            proveedor=self.proveedor,
            producto=self.producto,
            moneda=self.moneda,
            precio=Decimal("1500.0000"),
            cantidad_minima=Decimal("10.0000"),
            tiempo_entrega_dias=5,
        )

        self.diario_compras = Diario.objects.create(
            codigo="COMPRAS",
            nombre="Diario de Compras",
            tipo="compras",
        )

    def test_creacion_oc_y_totales(self):
        """Verifica el cálculo de subtotales, IVA y totales de una Orden de Compra."""
        oc = OrdenCompra.objects.create(
            numero="OC-TEST-001",
            proveedor=self.proveedor,
            fecha=date.today(),
            estado="borrador",
            condicion_pago=self.cond_pago,
            moneda=self.moneda,
        )

        linea = LineaOrdenCompra.objects.create(
            orden_compra=oc,
            producto=self.producto,
            cantidad=Decimal("100.0000"),
            precio_unitario=Decimal("1500.0000"),
            impuesto=self.iva21,
        )

        self.assertEqual(oc.subtotal, Decimal("150000.00"))
        self.assertEqual(oc.total_iva, Decimal("31500.00"))
        self.assertEqual(oc.total, Decimal("181500.00"))
        self.assertEqual(oc.estado_recepcion, "pendiente")
        self.assertEqual(oc.estado_facturacion, "pendiente")

    def test_confirmar_oc_genera_remito_recepcion(self):
        """Verifica que al confirmar la OC se genera el remito entrante en Almacén."""
        oc = OrdenCompra.objects.create(
            numero="OC-TEST-002",
            proveedor=self.proveedor,
            fecha=date.today(),
            estado="borrador",
            condicion_pago=self.cond_pago,
            moneda=self.moneda,
        )
        LineaOrdenCompra.objects.create(
            orden_compra=oc,
            producto=self.producto,
            cantidad=Decimal("50.0000"),
            precio_unitario=Decimal("1500.0000"),
        )

        remito = ComprasService.confirmar_oc(oc)
        oc.refresh_from_db()

        self.assertEqual(oc.estado, "confirmado")
        self.assertIsNotNone(remito)
        self.assertEqual(remito.tipo, "recepcion")
        self.assertEqual(remito.lineas.count(), 1)
        self.assertEqual(remito.lineas.first().cantidad, Decimal("50.0000"))

    def test_sincronizacion_recepcion_parcial_y_total_con_stock(self):
        """Verifica la recepción de mercadería con sincronización en tiempo real hacia la OC."""
        oc = OrdenCompra.objects.create(
            numero="OC-TEST-003",
            proveedor=self.proveedor,
            fecha=date.today(),
            estado="borrador",
            condicion_pago=self.cond_pago,
            moneda=self.moneda,
        )
        linea_oc = LineaOrdenCompra.objects.create(
            orden_compra=oc,
            producto=self.producto,
            cantidad=Decimal("100.0000"),
            precio_unitario=Decimal("1500.0000"),
        )

        remito = ComprasService.confirmar_oc(oc)
        linea_remito = remito.lineas.first()

        # Simular recepción parcial de 40 metros
        linea_remito.cantidad_hecha = Decimal("40.0000")
        linea_remito.estado = "realizado"
        linea_remito.save()

        # Al finalizar el remito
        remito.estado = "finalizado"
        remito.save()

        oc.actualizar_cantidades_recibidas()
        linea_oc.refresh_from_db()
        oc.refresh_from_db()

        self.assertEqual(linea_oc.cantidad_recibida, Decimal("40.0000"))
        self.assertEqual(linea_oc.cantidad_pendiente, Decimal("60.0000"))
        self.assertEqual(oc.estado_recepcion, "parcial")
        self.assertEqual(oc.porcentaje_recibido, Decimal("40.00"))
        self.assertEqual(oc.estado, "confirmado")

        # Simular segundo remito por los 60 restantes (backorder)
        remito_resto = MovimientoStock.objects.create(
            numero="REC-OC-TEST-003-BO",
            tipo="recepcion",
            estado="finalizado",
            contacto=self.proveedor,
            ubicacion_origen=self.ubicacion_prov,
            ubicacion_destino=self.almacen_interno,
            content_type_origen=remito.content_type_origen,
            object_id_origen=oc.id,
        )
        linea_resto = remito_resto.lineas.create(
            producto=self.producto,
            cantidad=Decimal("60.0000"),
            cantidad_hecha=Decimal("60.0000"),
            ubicacion_origen=self.ubicacion_prov,
            ubicacion_destino=self.almacen_interno,
            estado="realizado",
        )

        oc.actualizar_cantidades_recibidas()
        linea_oc.refresh_from_db()
        oc.refresh_from_db()

        self.assertEqual(linea_oc.cantidad_recibida, Decimal("100.0000"))
        self.assertEqual(oc.estado_recepcion, "completo")
        self.assertEqual(oc.estado, "finalizado")

    def test_cancelacion_oc_anula_remitos_pendientes(self):
        """Verifica que cancelar la OC anula los remitos de recepción en borrador/confirmados."""
        oc = OrdenCompra.objects.create(
            numero="OC-TEST-004",
            proveedor=self.proveedor,
            fecha=date.today(),
            estado="borrador",
            condicion_pago=self.cond_pago,
            moneda=self.moneda,
        )
        LineaOrdenCompra.objects.create(
            orden_compra=oc,
            producto=self.producto,
            cantidad=Decimal("20.0000"),
            precio_unitario=Decimal("1500.0000"),
        )
        remito = ComprasService.confirmar_oc(oc)
        self.assertEqual(remito.estado, "confirmado")

        ComprasService.cancelar_oc(oc)
        oc.refresh_from_db()
        remito.refresh_from_db()

        self.assertEqual(oc.estado, "cancelado")
        self.assertEqual(remito.estado, "cancelado")

    def test_facturacion_3_way_matching(self):
        """Verifica la generación de la Factura de Compra en Contabilidad a partir de lo recibido."""
        oc = OrdenCompra.objects.create(
            numero="OC-TEST-005",
            proveedor=self.proveedor,
            fecha=date.today(),
            estado="borrador",
            condicion_pago=self.cond_pago,
            moneda=self.moneda,
        )
        linea_oc = LineaOrdenCompra.objects.create(
            orden_compra=oc,
            producto=self.producto,
            cantidad=Decimal("10.0000"),
            precio_unitario=Decimal("2000.0000"),
            impuesto=self.iva21,
        )
        ComprasService.confirmar_oc(oc)

        # Simular recepción parcial de 5 unidades
        linea_oc.cantidad_recibida = Decimal("5.0000")
        linea_oc.save()

        # Generar factura de compra basada en lo recibido
        factura = ComprasService.crear_factura_proveedor(
            oc=oc,
            numero_factura="FC-A-0001-00099887",
            basado_en="recibido",
        )

        self.assertIsNotNone(factura)
        self.assertEqual(factura.tipo, "factura_proveedor")
        self.assertEqual(factura.orden_compra, oc)
        self.assertEqual(factura.monto_neto, Decimal("10000.00")) # 5 * 2000
        self.assertEqual(factura.monto_impuestos, Decimal("2100.00")) # 21% de 10000
        self.assertEqual(factura.monto_total, Decimal("12100.00"))

        linea_oc.refresh_from_db()
        self.assertEqual(linea_oc.cantidad_facturada, Decimal("5.0000"))
        self.assertEqual(oc.estado_facturacion, "parcial")

    def test_generador_pdf_orden_compra(self):
        """Verifica que el generador de PDF de la OC renderice el contexto correctamente."""
        oc = OrdenCompra.objects.create(
            numero="OC-TEST-006",
            proveedor=self.proveedor,
            fecha=date.today(),
            estado="confirmado",
            condicion_pago=self.cond_pago,
            moneda=self.moneda,
        )
        LineaOrdenCompra.objects.create(
            orden_compra=oc,
            producto=self.producto,
            cantidad=Decimal("15.0000"),
            precio_unitario=Decimal("1000.0000"),
            impuesto=self.iva21,
        )

        report = OrdenCompraPDFReport(oc)
        context = report.get_context_data()

        self.assertEqual(context["oc"], oc)
        self.assertEqual(context["proveedor"], self.proveedor)
        self.assertEqual(len(context["lineas"]), 1)
        self.assertTrue(report.nombre_archivo.startswith("Orden_Compra_OC-TEST-006"))

    def test_solicitud_cotizacion_rfq_y_reporte(self):
        """Verifica la emisión de una Solicitud de Cotización (RFQ) y su reporte PDF."""
        from apps.compras.reports import SolicitudCotizacionPDFReport

        rfq = OrdenCompra.objects.create(
            numero="RFQ-TEST-001",
            proveedor=self.proveedor,
            fecha=date.today(),
            estado="cotizacion",
            condicion_pago=self.cond_pago,
            moneda=self.moneda,
        )
        LineaOrdenCompra.objects.create(
            orden_compra=rfq,
            producto=self.producto,
            cantidad=Decimal("50.0000"),
            precio_unitario=Decimal("0.0000"),
        )

        self.assertEqual(rfq.estado, "cotizacion")
        report = SolicitudCotizacionPDFReport(rfq)
        context = report.get_context_data()
        self.assertEqual(context["oc"], rfq)
        self.assertTrue(report.nombre_archivo.startswith("Solicitud_Cotizacion_RFQ-TEST-001"))

        # Pasar de cotización a confirmado directamente al aprobar el presupuesto
        remito = ComprasService.confirmar_oc(rfq)
        rfq.refresh_from_db()
        self.assertEqual(rfq.estado, "confirmado")
        self.assertIsNotNone(remito)

    def test_reporte_recepciones_pendientes_backorders(self):
        """Verifica el cálculo del reporte tabular de recepciones pendientes."""
        from apps.compras.reports import RecepcionesPendientesExcelReport

        oc = OrdenCompra.objects.create(
            numero="OC-TEST-BACKORDER",
            proveedor=self.proveedor,
            fecha=date.today(),
            estado="confirmado",
            condicion_pago=self.cond_pago,
            moneda=self.moneda,
        )
        linea = LineaOrdenCompra.objects.create(
            orden_compra=oc,
            producto=self.producto,
            cantidad=Decimal("100.0000"),
            cantidad_recibida=Decimal("30.0000"),
            precio_unitario=Decimal("1500.0000"),
        )

        report = RecepcionesPendientesExcelReport(proveedor_id=self.proveedor.id)
        qs = list(report.get_queryset())
        self.assertIn(linea, qs)

        headers = report.get_headers()
        row = report.get_row_data(linea)

        self.assertIn("N° Orden Compra", headers)
        self.assertEqual(row[0], "OC-TEST-BACKORDER")
        self.assertEqual(row[9], 100.0) # Pedida
        self.assertEqual(row[10], 30.0) # Recibida
        self.assertEqual(row[11], 70.0) # Pendiente
