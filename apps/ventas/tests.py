from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from apps.base.models import ConfiguracionEmpresa
from apps.contactos.models import Contacto
from apps.inventario.models import Producto, Ubicacion
from apps.ventas.models import CanalVenta, OrdenVenta, LineaOrdenVenta
from apps.ventas.dtos import (
    OrdenVentaDTO,
    ClienteDTO,
    LineaOrdenDTO,
    RecargoDTO,
    CuponDTO,
)
from apps.ventas.services import VentasService
from apps.integraciones.woocommerce.models import TiendaWooCommerce
from apps.integraciones.woocommerce.normalizers import WooCommerceNormalizer


class VentasDesacopleTestCase(TestCase):
    def setUp(self):
        self.empresa = ConfiguracionEmpresa.get_solo()
        self.empresa.razon_social = "CALZADOS ARGENTINOS S.A."
        self.empresa.cuit = "30712345678"
        self.empresa.condicion_iva = "responsable_inscripto"
        self.empresa.save()

        self.almacen, _ = Ubicacion.objects.get_or_create(
            tipo="interna", nombre="Depósito Central"
        )

        self.producto = Producto.objects.create(
            sku="BORC-URB-42",
            nombre="Borceguí Urbano 42",
            precio_venta=Decimal("45000.00"),
            activo=True,
        )

        self.canal = CanalVenta.objects.create(
            empresa=self.empresa,
            nombre="Canal Tienda Online",
            codigo="WC-ONLINE",
            tipo="woocommerce",
            almacen_predeterminado=self.almacen,
            activo=True,
        )

    def test_ingesta_canonica_desacoplada_desde_dto(self):
        """
        Valida que el core de ventas procese un OrdenVentaDTO puro sin ninguna
        dependencia directa ni conocimiento de WooCommerce.
        """
        dto = OrdenVentaDTO(
            referencia_externa="ORD-9901",
            numero_externo="9901",
            estado_canal_externo="processing",
            cliente=ClienteDTO(
                nombre="Juan Perez",
                email="juan.perez@example.com",
                cuit="20334455667",
                telefono="1122334455",
                direccion="Av. Corrientes 1234",
                ciudad="CABA",
                provincia="CABA",
                condicion_iva="consumidor_final",
            ),
            lineas=[
                LineaOrdenDTO(
                    sku="BORC-URB-42",
                    cantidad=Decimal("2.00"),
                    precio_unitario=Decimal("45000.00"),
                    id_linea_externo="L-101",
                )
            ],
            recargos=[
                RecargoDTO(
                    nombre="Tasa Cuotas",
                    monto=Decimal("1500.00"),
                )
            ],
            cupones=[
                CuponDTO(
                    codigo="PROMO10",
                    monto_descuento=Decimal("4500.00"),
                )
            ],
            monto_total=Decimal("87000.00"),
            total_descuentos=Decimal("4500.00"),
            total_envio=Decimal("0.00"),
            total_impuestos=Decimal("0.00"),
            metodo_envio_titulo="Envío Estándar",
            metodo_pago="Mercado Pago",
            transaccion_id="MP-998877",
        )

        orden = VentasService.ingestar_orden_canal(self.canal, dto)

        self.assertIsNotNone(orden)
        self.assertEqual(orden.canal, self.canal)
        self.assertEqual(orden.referencia_externa, "ORD-9901")
        self.assertEqual(orden.numero_externo, "9901")
        self.assertEqual(orden.estado, "confirmado")
        self.assertEqual(orden.cliente.cuil, "20334455667")
        self.assertEqual(orden.monto_total, Decimal("87000.00"))
        self.assertEqual(orden.total_recargos_fees, Decimal("1500.00"))

        # Validar líneas
        self.assertEqual(orden.lineas.count(), 1)
        linea = orden.lineas.first()
        self.assertEqual(linea.producto, self.producto)
        self.assertEqual(linea.cantidad, Decimal("2.00"))
        self.assertEqual(linea.referencia_linea_externa, "L-101")

        # Validar compatibilidad regresiva con properties
        self.assertEqual(orden.wc_order_number, "9901")
        self.assertEqual(linea.wc_line_id, "L-101")

    def test_adaptador_woocommerce_normalizer_a_ingesta(self):
        """
        Valida que un payload crudo de WooCommerce sea traducido por WooCommerceNormalizer
        e ingestada por VentasService mediante el adaptador de integraciones.
        """
        tienda = TiendaWooCommerce.objects.create(
            empresa=self.empresa,
            canal_venta=self.canal,
            nombre="Tienda Oficial Woo",
            codigo_prefijo="WC-TEST",
            url="https://tienda.ejemplo.com",
            consumer_key="ck_test123",
            consumer_secret="cs_test123",
            webhook_secret="whsec_123",
        )

        payload_woo = {
            "id": 12345,
            "number": "12345",
            "status": "processing",
            "total": "47500.00",
            "discount_total": "0.00",
            "shipping_total": "2500.00",
            "total_tax": "0.00",
            "payment_method_title": "MercadoPago Tarjeta",
            "transaction_id": "MP-TRX-12345",
            "billing": {
                "first_name": "CARLOS",
                "last_name": "GOMEZ",
                "email": "carlos.gomez@empresa.com",
                "phone": "011-5555-4444",
                "address_1": "San Martín 450",
                "city": "La Plata",
                "state": "Buenos Aires",
                "postcode": "1900",
            },
            "meta_data": [
                {"key": "_billing_cuit", "value": "20301112224"},
                {"key": "_billing_condicion_iva", "value": "responsable_inscripto"},
            ],
            "line_items": [
                {
                    "id": 8801,
                    "name": "Borceguí Urbano 42",
                    "sku": "BORC-URB-42",
                    "quantity": 1,
                    "price": "45000.00",
                }
            ],
            "shipping_lines": [
                {
                    "method_title": "Correo Argentino Clásico",
                    "method_id": "correo_argentino",
                }
            ],
            "fee_lines": [],
            "coupon_lines": [],
        }

        # Ingesta vía adaptador de compatibilidad
        orden = VentasService.procesar_orden_woocommerce(tienda.id, payload_woo)

        self.assertIsNotNone(orden)
        self.assertEqual(orden.canal, self.canal)
        self.assertEqual(orden.referencia_externa, "12345")
        self.assertEqual(orden.cliente.cuil, "20301112224")
        self.assertEqual(orden.cliente.condicion_iva, "responsable_inscripto")
        self.assertEqual(orden.total_envio, Decimal("2500.00"))
        self.assertEqual(orden.metodo_envio_titulo, "Correo Argentino Clásico")
        self.assertEqual(orden.estado, "confirmado")

    def test_generar_remito_salida_y_reserva_stock(self):
        """
        Valida que al confirmar una Orden de Venta se genere el Remito de Salida (REM-OV-...)
        y se reserve el stock correspondiente en el almacén predeterminado del canal.
        """
        from apps.inventario.models import MovimientoStock, StockQuant
        from apps.ventas.models import LineaOrdenVenta

        # Inicializar StockQuant con 10 unidades físicas en mano
        StockQuant.objects.create(
            producto=self.producto,
            ubicacion=self.almacen,
            cantidad_fisica=Decimal("10.0"),
            cantidad_reservada=Decimal("0.0"),
        )

        cliente = Contacto.objects.create(
            codigo="CLI-TEST-2", nombre="Comprador Final", tipo="cliente"
        )
        orden = OrdenVenta.objects.create(
            canal=self.canal,
            numero="OV-TEST-200",
            cliente=cliente,
            estado="borrador",
            monto_total=Decimal("45000.00"),
        )
        LineaOrdenVenta.objects.create(
            orden=orden,
            producto=self.producto,
            cantidad=Decimal("3.0"),
            precio_unitario=Decimal("45000.00"),
        )

        # Confirmar la orden y generar remito
        remito = VentasService.generar_remito_salida(orden)

        self.assertIsNotNone(remito)
        self.assertEqual(remito.tipo, "entrega")
        self.assertEqual(remito.ubicacion_origen, self.almacen)
        self.assertEqual(remito.contacto, cliente)
        self.assertEqual(remito.lineas.count(), 1)

        # Verificar que el stock fue reservado: física=10, reservada=3, disponible=7
        quant = StockQuant.objects.get(producto=self.producto, ubicacion=self.almacen)
        self.assertEqual(quant.cantidad_fisica, Decimal("10.0"))
        self.assertEqual(quant.cantidad_reservada, Decimal("3.0"))
        self.assertEqual(quant.cantidad_disponible, Decimal("7.0"))

    def test_cancelar_orden_cancela_reservas_de_stock(self):
        """
        Valida que al cancelar una orden mediante eliminar_orden_woocommerce
        se liberen las reservas de stock en el inventario.
        """
        from apps.inventario.models import StockQuant
        from apps.ventas.models import LineaOrdenVenta

        StockQuant.objects.create(
            producto=self.producto,
            ubicacion=self.almacen,
            cantidad_fisica=Decimal("20.0"),
            cantidad_reservada=Decimal("0.0"),
        )

        tienda = TiendaWooCommerce.objects.create(
            empresa=self.empresa,
            canal_venta=self.canal,
            nombre="Tienda Test Cancel",
            codigo_prefijo="WC-CANC",
            url="https://tienda-canc.com",
            consumer_key="ck_1",
            consumer_secret="cs_1",
        )

        cliente = Contacto.objects.create(
            codigo="CLI-TEST-3", nombre="Comprador Cancel", tipo="cliente"
        )
        orden = OrdenVenta.objects.create(
            canal=self.canal,
            referencia_externa="9999",
            numero="WC-CANC-9999",
            cliente=cliente,
            estado="confirmado",
            monto_total=Decimal("45000.00"),
        )
        LineaOrdenVenta.objects.create(
            orden=orden,
            producto=self.producto,
            cantidad=Decimal("5.0"),
            precio_unitario=Decimal("45000.00"),
        )
        VentasService.generar_remito_salida(orden)

        # Chequear que se reservaron 5 unidades
        quant = StockQuant.objects.get(producto=self.producto, ubicacion=self.almacen)
        self.assertEqual(quant.cantidad_reservada, Decimal("5.0"))

        # Ejecutar cancelación
        VentasService.eliminar_orden_woocommerce(tienda.id, {"id": 9999})

        orden.refresh_from_db()
        self.assertEqual(orden.estado, "cancelado")

        # Chequear que la reserva fue liberada: reservada vuelve a 0
        quant.refresh_from_db()
        self.assertEqual(quant.cantidad_reservada, Decimal("0.0"))
        self.assertEqual(quant.cantidad_disponible, Decimal("20.0"))

    def test_presupuesto_y_nota_de_pedido_pdf(self):
        """
        Verifica la creación de una cotización/presupuesto con fecha de validez
        y la generación de su reporte PDF comercial antes de pasar a confirmado.
        """
        from apps.ventas.reports import PresupuestoPDFReport
        from datetime import date, timedelta

        cliente = Contacto.objects.create(
            codigo="CLI-TEST-PRE",
            nombre="Cliente Mayorista Presupuesto",
            tipo="cliente",
        )
        orden = OrdenVenta.objects.create(
            canal=self.canal,
            numero="PRE-2026-0001",
            cliente=cliente,
            estado="presupuesto",
            fecha_validez=date.today() + timedelta(days=15),
            subtotal_productos=Decimal("50000.00"),
            monto_total=Decimal("50000.00"),
        )
        LineaOrdenVenta.objects.create(
            orden=orden,
            producto=self.producto,
            cantidad=Decimal("2.0"),
            precio_unitario=Decimal("25000.00"),
            subtotal=Decimal("50000.00"),
            total_linea=Decimal("50000.00"),
        )

        self.assertEqual(orden.estado, "presupuesto")

        # Probar generación de Presupuesto PDF
        report = PresupuestoPDFReport(orden)
        context = report.get_context_data()
        self.assertTrue(context["es_presupuesto"])
        self.assertEqual(context["titulo_documento"], "PRESUPUESTO / COTIZACIÓN")
        self.assertTrue(report.nombre_archivo.startswith("Presupuesto_PRE-2026-0001"))

        # Pasar a nota de pedido o confirmado
        orden.estado = "confirmado"
        orden.save(update_fields=["estado"])
        report_pedido = PresupuestoPDFReport(orden)
        context_pedido = report_pedido.get_context_data()
        self.assertFalse(context_pedido["es_presupuesto"])
        self.assertEqual(context_pedido["titulo_documento"], "NOTA DE PEDIDO")
        self.assertTrue(
            report_pedido.nombre_archivo.startswith("Nota_Pedido_PRE-2026-0001")
        )
