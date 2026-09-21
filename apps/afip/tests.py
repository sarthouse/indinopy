from unittest.mock import patch, MagicMock
from django.test import TestCase
from apps.base.models import ConfiguracionEmpresa
from apps.afip.padron import PadronAFIPService
from apps.afip.dtos import ContribuyentePadronDTO
from apps.contactos.models import Contacto
from apps.contactos.afip_sync import ContactosAFIPService


class PadronAFIPTests(TestCase):
    def setUp(self):
        self.config = ConfiguracionEmpresa.get_solo()
        self.config.cuit = "20-11111111-2"
        self.config.save()

    def test_valida_longitud_cuit(self):
        with self.assertRaises(ValueError):
            PadronAFIPService.consultar_cuit("123")  # CUIT inválido

    @patch("apps.afip.client.AFIPClientFactory.get_client")
    def test_normalizacion_respuesta_monotributista(self, mock_get_client):
        mock_afip = MagicMock()
        mock_get_client.return_value = mock_afip

        mock_afip.RegisterScopeThirteen.getTaxpayerDetails.return_value = {
            "datosGenerales": {
                "razonSocial": "GONZALEZ JUAN PABLO",
                "tipoPersona": "FISICA",
                "estadoClave": "ACTIVO",
                "domicilioFiscal": {
                    "direccion": "Av. San Martín 1234",
                    "localidad": "Lanús",
                    "descripcionProvincia": "Buenos Aires",
                    "codPostal": 1824
                }
            },
            "datosMonotributo": {
                "categoriaMonotributo": {
                    "descripcionCategoria": "C"
                }
            }
        }

        dto = PadronAFIPService.consultar_cuit("20301234567", usar_cache=False)

        self.assertIsNotNone(dto)
        self.assertEqual(dto.cuit, "20301234567")
        self.assertEqual(dto.nombre_razon_social, "GONZALEZ JUAN PABLO")
        self.assertEqual(dto.condicion_iva, "RESPONSABLE_MONOTRIBUTO")
        self.assertTrue(dto.es_monotributista)
        self.assertEqual(dto.categoria_monotributo, "C")
        self.assertEqual(dto.localidad, "Lanús")

    @patch("apps.afip.client.AFIPClientFactory.get_client")
    def test_normalizacion_responsable_inscripto(self, mock_get_client):
        mock_afip = MagicMock()
        mock_get_client.return_value = mock_afip

        mock_afip.RegisterScopeThirteen.getTaxpayerDetails.return_value = {
            "datosGenerales": {
                "razonSocial": "INDUSTRIA CALZADO ARGENTINO S.A.",
                "tipoPersona": "JURIDICA",
                "estadoClave": "ACTIVO",
            },
            "datosRegimenGeneral": {
                "impuesto": [
                    {"idImpuesto": 30, "descripcionImpuesto": "IVA"},
                    {"idImpuesto": 10, "descripcionImpuesto": "GANANCIAS SOCIEDADES"}
                ]
            }
        }

        dto = PadronAFIPService.consultar_cuit("30711234568", usar_cache=False)

        self.assertIsNotNone(dto)
        self.assertEqual(dto.condicion_iva, "RESPONSABLE_INSCRIPTO")
        self.assertTrue(dto.es_responsable_inscripto)
        self.assertFalse(dto.es_monotributista)

    @patch.object(PadronAFIPService, "consultar_cuit")
    def test_sincronizar_contacto_con_afip(self, mock_consultar):
        mock_consultar.return_value = ContribuyentePadronDTO(
            cuit="20351234567",
            nombre_razon_social="RODRIGUEZ ESTEBAN",
            tipo_persona="FISICA",
            estado_clave="ACTIVO",
            condicion_iva="RESPONSABLE_INSCRIPTO",
            direccion="Calle Falsa 123",
            localidad="Avellaneda",
            provincia="Buenos Aires",
            codigo_postal="1870",
            es_responsable_inscripto=True,
        )

        contacto = Contacto.objects.create(
            codigo="CLI-TEST-001",
            nombre="CLI-TEMPORAL",
            cuil="20351234567"
        )

        res = ContactosAFIPService.sincronizar_contacto_con_afip(contacto)
        self.assertTrue(res)

        contacto.refresh_from_db()
        self.assertEqual(contacto.nombre, "RODRIGUEZ ESTEBAN")
        self.assertEqual(contacto.condicion_iva, "responsable_inscripto")
        self.assertEqual(contacto.direccion, "Calle Falsa 123")
        self.assertEqual(contacto.ciudad, "Avellaneda")

    def test_validacion_fce_exige_cbu_y_vencimiento(self):
        from apps.afip.facturacion import FacturadorAFIP
        from apps.contabilidad.models import DocumentoDeuda, TipoComprobanteAFIP, Diario
        from django.utils import timezone

        tipo_fce, _ = TipoComprobanteAFIP.objects.get_or_create(
            codigo="201",
            defaults={"nombre": "Factura de Crédito Electrónica MiPyME A", "letra": "A", "clasificacion_interna": "factura", "es_mipyme_fce": True}
        )
        diario, _ = Diario.objects.get_or_create(
            codigo="VENTAS_E",
            defaults={"nombre": "Ventas Electrónicas", "tipo": "venta", "es_facturacion_electronica": True, "punto_venta_afip": 1}
        )
        contacto = Contacto.objects.create(codigo="CLI-FCE", nombre="GRAN EMPRESA S.A.", cuil="30700000001")

        doc = DocumentoDeuda.objects.create(
            diario=diario,
            tipo="factura_cliente",
            tipo_comprobante_afip=tipo_fce,
            contacto=contacto,
            fecha_emision=timezone.now().date(),
            monto_neto=1000000,
            monto_total=1210000,
            cbu_emisor="",  # Falta CBU
        )

        facturador = FacturadorAFIP()
        with self.assertRaises(ValueError) as ctx:
            facturador.emitir_comprobante(doc)

        self.assertIn("exige", str(ctx.exception).lower())

    def test_libro_iva_excel_report_generacion(self):
        from apps.contabilidad.reports.libro_iva_report import LibroIVAVentasExcelReport
        from apps.contabilidad.models import DocumentoDeuda, TipoComprobanteAFIP, Diario
        from django.utils import timezone

        tipo_a, _ = TipoComprobanteAFIP.objects.get_or_create(
            codigo="001",
            defaults={"nombre": "Factura A", "letra": "A", "clasificacion_interna": "factura"}
        )
        diario, _ = Diario.objects.get_or_create(
            codigo="VENTAS_E",
            defaults={"nombre": "Ventas", "tipo": "venta", "punto_venta_afip": 1}
        )
        contacto = Contacto.objects.create(codigo="CLI-001", nombre="CLIENTE PRUEBA", cuil="30711111112", condicion_iva="responsable_inscripto")

        DocumentoDeuda.objects.create(
            diario=diario,
            tipo="factura_cliente",
            tipo_comprobante_afip=tipo_a,
            contacto=contacto,
            numero="0001-00000001",
            fecha_emision=timezone.now().date(),
            monto_neto=1000,
            monto_impuestos=210,
            monto_total=1210,
            estado="publicado",
            afip_cae="12345678901234",
        )

        reporte = LibroIVAVentasExcelReport()
        headers = reporte.get_headers()
        rows = reporte.get_rows()

        self.assertIn("Neto Gravado", headers)
        self.assertIn("Total Facturado", headers)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][3], "00000001")
        self.assertEqual(rows[0][6], "CLIENTE PRUEBA")
        self.assertEqual(rows[0][8], 1000.0)
        self.assertEqual(rows[0][14], 1210.0)

        # Probar render binario (Excel o fallback CSV)
        binario = reporte.render()
        self.assertGreater(len(binario), 0)

    def test_validacion_fiscal_incompatible(self):
        """Valida que una empresa Monotributista no pueda emitir Facturas A ni B."""
        empresa = ConfiguracionEmpresa.get_solo()
        empresa.condicion_iva = "monotributista"
        empresa.save()

        contacto = Contacto.objects.create(codigo="CLI-002", nombre="CLIENTE RI", cuil="30711111112", condicion_iva="responsable_inscripto")
        tipo_a, _ = TipoComprobanteAFIP.objects.get_or_create(codigo="001", defaults={"nombre": "Factura A", "letra": "A"})

        with self.assertRaises(ValueError) as ctx:
            FacturadorAFIP.validar_compatibilidad_fiscal(empresa, contacto, tipo_a)
        self.assertIn("Monotributista", str(ctx.exception))

    def test_comprobante_fiscal_pdf_render(self):
        """Prueba el renderizado del template unificado de comprobante fiscal con QR."""
        from apps.contabilidad.reports.comprobante_report import ComprobanteFiscalPDFReport

        empresa = ConfiguracionEmpresa.get_solo()
        empresa.condicion_iva = "responsable_inscripto"
        empresa.ingresos_brutos = "30-71111111-2"
        empresa.save()

        tipo_a, _ = TipoComprobanteAFIP.objects.get_or_create(codigo="001", defaults={"nombre": "Factura A", "letra": "A"})
        diario, _ = Diario.objects.get_or_create(codigo="VEN_TEST", defaults={"nombre": "Ventas Test", "tipo": "ventas", "punto_venta_afip": 1})
        contacto = Contacto.objects.create(codigo="CLI-003", nombre="COMPRADOR S.A.", cuil="30999999991", condicion_iva="responsable_inscripto")

        doc = DocumentoDeuda.objects.create(
            diario=diario,
            tipo="factura_cliente",
            tipo_comprobante_afip=tipo_a,
            contacto=contacto,
            numero="0001-00000042",
            fecha_emision=timezone.now().date(),
            monto_neto=5000,
            monto_impuestos=1050,
            monto_total=6050,
            estado="publicado",
            afip_cae="74123456789012",
            afip_vencimiento_cae=timezone.now().date(),
        )

        report = ComprobanteFiscalPDFReport(doc)
        ctx = report.get_context_data()
        self.assertEqual(ctx["letra"], "A")
        self.assertTrue(ctx["discrimina_iva"])
        self.assertIsNotNone(ctx["qr_data_uri"])

        # Renderizar HTML
        html = report.render()
        self.assertIn("FACTURA", html)
        self.assertIn("74123456789012", html)
        self.assertIn("Responsable Inscripto", html)

    def test_nota_credito_creacion_y_payload_cbtes_asoc(self):
        """Valida que la Nota de Crédito vincule el comprobante asociado y arme CbtesAsoc para AFIP."""
        from apps.contabilidad.services import ContabilidadService
        from apps.contabilidad.reports.comprobante_report import ComprobanteFiscalPDFReport

        empresa = ConfiguracionEmpresa.get_solo()
        empresa.condicion_iva = "responsable_inscripto"
        empresa.save()

        tipo_a, _ = TipoComprobanteAFIP.objects.get_or_create(codigo="001", defaults={"nombre": "Factura A", "letra": "A", "clasificacion_interna": "factura"})
        TipoComprobanteAFIP.objects.get_or_create(codigo="003", defaults={"nombre": "Nota de Crédito A", "letra": "A", "clasificacion_interna": "nota_credito"})

        diario, _ = Diario.objects.get_or_create(codigo="VEN_NC", defaults={"nombre": "Ventas NC", "tipo": "ventas", "punto_venta_afip": 1})
        contacto = Contacto.objects.create(codigo="CLI-004", nombre="CLIENTE NC S.A.", cuil="30999999991", condicion_iva="responsable_inscripto")

        factura = DocumentoDeuda.objects.create(
            diario=diario,
            tipo="factura_cliente",
            tipo_comprobante_afip=tipo_a,
            contacto=contacto,
            numero="0001-00000088",
            fecha_emision=timezone.now().date(),
            monto_neto=2000,
            monto_impuestos=420,
            monto_total=2420,
            estado="publicado",
            afip_cae="99123456789012",
        )

        # Crear Nota de Crédito
        nc = ContabilidadService.crear_nota_credito_desde_comprobante(factura, motivo="Devolución total")
        self.assertEqual(nc.tipo, "nota_credito_cliente")
        self.assertEqual(nc.comprobante_asociado, factura)
        self.assertEqual(nc.tipo_comprobante_afip.codigo, "003")
        self.assertEqual(nc.monto_total, factura.monto_total)

        # Probar render de reporte PDF de la NC
        report = ComprobanteFiscalPDFReport(nc)
        ctx = report.get_context_data()
        self.assertTrue(ctx["es_nota_credito"])
        self.assertEqual(ctx["titulo_documento"], "NOTA DE CRÉDITO")

        html = report.render()
        self.assertIn("NOTA DE CRÉDITO", html)
        self.assertIn("0001-00000088", html)

    def test_comprobante_fiscal_con_descuentos_y_recargos(self):
        """Valida que el reporte PDF desglose adecuadamente los descuentos y recargos."""
        from apps.contabilidad.reports.comprobante_report import ComprobanteFiscalPDFReport

        tipo_b, _ = TipoComprobanteAFIP.objects.get_or_create(codigo="006", defaults={"nombre": "Factura B", "letra": "B", "clasificacion_interna": "factura"})
        diario, _ = Diario.objects.get_or_create(codigo="VEN_B", defaults={"nombre": "Ventas B", "tipo": "ventas", "punto_venta_afip": 1})
        contacto = Contacto.objects.create(codigo="CLI-005", nombre="CONSUMIDOR FINAL", cuil="20123456789", condicion_iva="consumidor_final")

        factura = DocumentoDeuda.objects.create(
            diario=diario,
            tipo="factura_cliente",
            tipo_comprobante_afip=tipo_b,
            contacto=contacto,
            numero="0001-00000150",
            fecha_emision=timezone.now().date(),
            monto_neto=10000,
            monto_descuentos=1500,
            monto_recargos=300,
            monto_impuestos=1848,
            monto_total=10648,
            estado="publicado",
            afip_cae="11223344556677",
            afip_vencimiento_cae=timezone.now().date(),
        )

        report = ComprobanteFiscalPDFReport(factura)
        html = report.render()
        self.assertIn("Descuentos / Cupones:", html)
        self.assertIn("1500.00", html)
        self.assertIn("Recargos / Tasas:", html)
        self.assertIn("300.00", html)

    def test_tributos_percepciones_y_transparencia_fiscal(self):
        """Valida la inyección de Tributos (ImpTrib) y el cumplimiento de la Ley 27.743 de Transparencia Fiscal."""
        from apps.contabilidad.models import TributoDocumentoDeuda
        from apps.contabilidad.reports.comprobante_report import ComprobanteFiscalPDFReport

        tipo_b, _ = TipoComprobanteAFIP.objects.get_or_create(codigo="006", defaults={"nombre": "Factura B", "letra": "B", "clasificacion_interna": "factura"})
        diario, _ = Diario.objects.get_or_create(codigo="VEN_TRIB", defaults={"nombre": "Ventas Trib", "tipo": "ventas", "punto_venta_afip": 1})
        contacto = Contacto.objects.create(codigo="CLI-006", nombre="JUAN PEREZ", cuil="20333333339", condicion_iva="consumidor_final")

        factura = DocumentoDeuda.objects.create(
            diario=diario,
            tipo="factura_cliente",
            tipo_comprobante_afip=tipo_b,
            contacto=contacto,
            numero="0001-00000200",
            fecha_emision=timezone.now().date(),
            monto_neto=10000,
            monto_impuestos=2100,
            monto_tributos=350,
            monto_total=12450,
            estado="publicado",
            afip_cae="88776655443322",
            afip_vencimiento_cae=timezone.now().date(),
        )

        TributoDocumentoDeuda.objects.create(
            documento=factura,
            afip_tributo_id=2,
            descripcion="Percepción IIBB Buenos Aires (3.5%)",
            base_imponible=10000,
            alicuota=3.5,
            importe=350,
        )

        report = ComprobanteFiscalPDFReport(factura)
        html = report.render()

        # Validar desglose de percepción
        self.assertIn("Percepción IIBB Buenos Aires (3.5%):", html)
        self.assertIn("350.00", html)

        # Validar cumplimiento del Régimen de Transparencia Fiscal al Consumidor (Ley 27.743)
        self.assertIn("RÉGIMEN DE TRANSPARENCIA FISCAL AL CONSUMIDOR (Ley N° 27.743 / RG 5614/2024)", html)
        self.assertIn("IVA Contenido:", html)
        self.assertIn("2100.00", html)
        self.assertIn("Otros Tributos Nacionales Indirectos:", html)

    def test_compras_percepciones_contabilizacion_y_libro_iva_compras(self):
        """
        Valida que una factura de proveedor con percepciones sufridas (IIBB e IVA):
        1. Se registre con sus tributos asociados.
        2. Se contabilice en el Libro Diario imputando la cuenta de activo tributario (crédito fiscal).
        3. Se exporte e incluya en el Libro IVA Compras Digital.
        """
        from apps.contabilidad.models import (
            Cuenta,
            ConfiguracionContable,
            Impuesto,
            TributoDocumentoDeuda,
            LineaDocumentoDeuda,
        )
        from apps.contabilidad.contabilizacion import ContabilizacionDocumentoService
        from apps.contabilidad.reports.libro_iva_report import LibroIVAComprasExcelReport

        empresa = ConfiguracionEmpresa.get_solo()
        empresa.condicion_iva = "responsable_inscripto"
        empresa.save()

        # Cuentas contables para la prueba
        cta_prov, _ = Cuenta.objects.get_or_create(codigo="2.1.01", defaults={"nombre": "Proveedores Locales", "tipo": "pasivo", "naturaleza": "acreedora", "imputable": True})
        cta_gasto, _ = Cuenta.objects.get_or_create(codigo="5.1.01", defaults={"nombre": "Compra Materia Prima", "tipo": "resultado_negativo", "naturaleza": "deudora", "imputable": True})
        cta_iva_cf, _ = Cuenta.objects.get_or_create(codigo="1.1.05", defaults={"nombre": "IVA Crédito Fiscal", "tipo": "activo", "naturaleza": "deudora", "imputable": True})
        cta_percep_iibb, _ = Cuenta.objects.get_or_create(codigo="1.1.06", defaults={"nombre": "Percepciones IIBB Sufridas", "tipo": "activo", "naturaleza": "deudora", "imputable": True})
        cta_clientes, _ = Cuenta.objects.get_or_create(codigo="1.1.02", defaults={"nombre": "Deudores por Ventas", "tipo": "activo", "naturaleza": "deudora", "imputable": True})
        cta_ventas, _ = Cuenta.objects.get_or_create(codigo="4.1.01", defaults={"nombre": "Ventas de Calzado", "tipo": "resultado_positivo", "naturaleza": "acreedora", "imputable": True})

        ConfiguracionContable.objects.get_or_create(
            empresa=empresa,
            defaults={
                "cuenta_clientes_defecto": cta_clientes,
                "cuenta_proveedores_defecto": cta_prov,
                "cuenta_ventas_defecto": cta_ventas,
                "cuenta_gastos_defecto": cta_gasto,
            },
        )

        imp_iva_21, _ = Impuesto.objects.get_or_create(
            nombre="IVA Compras 21%",
            defaults={"tipo": "iva", "alicuota": Decimal("21.00"), "cuenta_imputacion": cta_iva_cf, "afip_id": 5}
        )
        imp_percep_iibb, _ = Impuesto.objects.get_or_create(
            nombre="Percepción IIBB Sufrida",
            defaults={"tipo": "percepcion_iibb", "alicuota": Decimal("3.00"), "cuenta_imputacion": cta_percep_iibb}
        )

        diario_compras, _ = Diario.objects.get_or_create(
            codigo="COM_TEST",
            defaults={"nombre": "Diario Compras Test", "tipo": "compras", "es_facturacion_electronica": False}
        )
        tipo_factura_a, _ = TipoComprobanteAFIP.objects.get_or_create(
            codigo="001",
            defaults={"nombre": "Factura A", "letra": "A", "clasificacion_interna": "factura"}
        )
        proveedor = Contacto.objects.create(
            codigo="PRV-001",
            nombre="CURTIEMBRE CENTRAL S.A.",
            cuil="30555555551",
            tipo="proveedor",
            condicion_iva="responsable_inscripto"
        )

        factura_compra = DocumentoDeuda.objects.create(
            diario=diario_compras,
            tipo="factura_proveedor",
            tipo_comprobante_afip=tipo_factura_a,
            contacto=proveedor,
            numero="0003-00012345",
            fecha_emision=timezone.now().date(),
            monto_neto=Decimal("10000.00"),
            monto_impuestos=Decimal("2100.00"),
            monto_tributos=Decimal("300.00"),
            monto_total=Decimal("12400.00"),
            estado="publicado",
        )

        LineaDocumentoDeuda.objects.create(
            documento=factura_compra,
            descripcion="Cuero Vacuno Flor Premium",
            cantidad=Decimal("10.00"),
            precio_unitario=Decimal("1000.00"),
            impuesto=imp_iva_21,
            subtotal=Decimal("10000.00"),
        )

        TributoDocumentoDeuda.objects.create(
            documento=factura_compra,
            afip_tributo_id=2,  # IIBB
            descripcion="Percepción IIBB ARBA 3%",
            base_imponible=Decimal("10000.00"),
            alicuota=Decimal("3.00"),
            importe=Decimal("300.00"),
            impuesto=imp_percep_iibb,
        )

        # 1. Validar contabilización automática
        asiento = ContabilizacionDocumentoService.contabilizar_factura(factura_compra)
        self.assertIsNotNone(asiento)
        self.assertEqual(asiento.estado, "asentado")

        apuntes = list(asiento.apuntes.all())
        # Debe: Gasto $10000, IVA CF $2100, Percep IIBB $300 | Haber: Proveedores $12400
        total_debe = sum(a.debe for a in apuntes)
        total_haber = sum(a.haber for a in apuntes)
        self.assertEqual(total_debe, Decimal("12400.00"))
        self.assertEqual(total_haber, Decimal("12400.00"))

        apunte_percep = next((a for a in apuntes if a.cuenta == cta_percep_iibb), None)
        self.assertIsNotNone(apunte_percep)
        self.assertEqual(apunte_percep.debe, Decimal("300.00"))

        # 2. Validar inclusión en Libro IVA Compras
        reporte_compras = LibroIVAComprasExcelReport()
        headers = reporte_compras.get_headers()
        rows = reporte_compras.get_rows()

        self.assertIn("Total Crédito IVA", headers)
        self.assertIn("Percepción IIBB", headers)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row[3], "00012345")
        self.assertEqual(row[6], "CURTIEMBRE CENTRAL S.A.")
        self.assertEqual(row[8], 10000.0)
        self.assertEqual(row[13], 2100.0)
        self.assertEqual(row[15], 300.0)
        self.assertEqual(row[17], 12400.0)

    def test_generar_factura_desde_orden_con_descuentos_y_recargos(self):
        """
        Valida que VentasService.generar_factura_desde_orden:
        1. Cree la factura B para consumidor final con ítems, descuentos y recargos desglosados.
        2. Calcule los totales netos, IVA y tributos adecuadamente.
        3. Enlace la orden_venta con el comprobante de deuda generado.
        """
        from apps.ventas.models import OrdenVenta, LineaOrdenVenta, LineaRecargoOrden
        from apps.ventas.services import VentasService
        from apps.inventario.models import Producto

        empresa = ConfiguracionEmpresa.get_solo()
        empresa.condicion_iva = "responsable_inscripto"
        empresa.save()

        cliente = Contacto.objects.create(
            codigo="CLI-CF-01",
            nombre="MARIA LOPEZ",
            cuil="27400000001",
            tipo="CLIENTE",
            condicion_iva="consumidor_final",
        )

        producto, _ = Producto.objects.get_or_create(
            sku="BORCEGUI-VAGNER-41",
            defaults={"nombre": "Borceguí Vagner Cuero 41", "precio_venta": Decimal("50000.00")}
        )

        orden = OrdenVenta.objects.create(
            numero="OV-TEST-100",
            cliente=cliente,
            subtotal_productos=Decimal("50000.00"),
            total_descuentos=Decimal("5000.00"),  # Cupón $5000
            total_envio=Decimal("2500.00"),       # Envío $2500
            total_recargos_fees=Decimal("1500.00"), # Recargo pasarela $1500
            monto_total=Decimal("49000.00"),
            estado="confirmado",
        )

        LineaOrdenVenta.objects.create(
            orden=orden,
            producto=producto,
            cantidad=Decimal("1.00"),
            precio_unitario=Decimal("50000.00"),
            descuento=Decimal("5000.00"),
        )

        LineaRecargoOrden.objects.create(
            orden=orden,
            nombre="Tasa Cuotas MercadoPago",
            monto=Decimal("1500.00"),
        )

        # Generar factura desde la orden de venta
        factura = VentasService.generar_factura_desde_orden(orden)

        self.assertIsNotNone(factura)
        self.assertEqual(factura.contacto, cliente)
        self.assertEqual(factura.tipo_comprobante_afip.letra, "B")
        self.assertEqual(factura.orden_venta, orden)
        self.assertEqual(factura.monto_descuentos, Decimal("5000.00"))
        self.assertEqual(factura.monto_recargos, Decimal("4000.00"))  # 2500 envio + 1500 fee

        # Validar líneas creadas en el comprobante fiscal
        lineas = list(factura.lineas.all())
        self.assertEqual(len(lineas), 3)  # Producto + Envío + Recargo
        self.assertTrue(any("Envío a domicilio" in l.descripcion for l in lineas))
        self.assertTrue(any("Recargo: Tasa Cuotas" in l.descripcion for l in lineas))

    def test_nota_debito_creacion_y_render_pdf(self):
        """
        Valida que una Nota de Débito:
        1. Se cree vinculada a su comprobante original mediante crear_nota_debito_desde_comprobante.
        2. Adopte el tipo de comprobante AFIP correspondiente a la misma letra (ej: Tipo 002 para ND A).
        3. Se contabilice en el Libro Diario (Deudores al Debe, Ingreso por intereses e IVA Débito al Haber).
        4. Renderice en el PDF oficial el título 'NOTA DE DÉBITO' y el comprobante original asociado.
        """
        from apps.contabilidad.services import ContabilidadService
        from apps.contabilidad.contabilizacion import ContabilizacionDocumentoService
        from apps.contabilidad.reports.comprobante_report import ComprobanteFiscalPDFReport

        empresa = ConfiguracionEmpresa.get_solo()
        empresa.condicion_iva = "responsable_inscripto"
        empresa.save()

        tipo_a, _ = TipoComprobanteAFIP.objects.get_or_create(
            codigo="001", defaults={"nombre": "Factura A", "letra": "A", "clasificacion_interna": "factura"}
        )
        tipo_nd_a, _ = TipoComprobanteAFIP.objects.get_or_create(
            codigo="002", defaults={"nombre": "Nota de Débito A", "letra": "A", "clasificacion_interna": "nota_debito"}
        )
        diario, _ = Diario.objects.get_or_create(
            codigo="VEN_ND", defaults={"nombre": "Ventas ND", "tipo": "ventas", "punto_venta_afip": 1}
        )
        cliente = Contacto.objects.create(
            codigo="CLI-RI-ND", nombre="DISTRIBUIDORA SUR S.A.", cuil="30888888882", condicion_iva="responsable_inscripto"
        )

        factura = DocumentoDeuda.objects.create(
            diario=diario,
            tipo="factura_cliente",
            tipo_comprobante_afip=tipo_a,
            contacto=cliente,
            numero="0001-00000550",
            fecha_emision=timezone.now().date(),
            monto_neto=Decimal("100000.00"),
            monto_impuestos=Decimal("21000.00"),
            monto_total=Decimal("121000.00"),
            estado="publicado",
            afip_cae="99887766554433",
            afip_vencimiento_cae=timezone.now().date(),
        )

        # 1. Crear Nota de Débito por intereses moratorios ($5000 + IVA 21% + Percepción IIBB 3.5%)
        imp_percep_iibb, _ = Impuesto.objects.get_or_create(
            nombre="Percepción IIBB Ventas",
            defaults={"tipo": "percepcion_iibb", "alicuota": Decimal("3.50"), "cuenta_imputacion": None}
        )
        nd = ContabilidadService.crear_nota_debito_desde_comprobante(
            factura_original=factura,
            motivo="Intereses por pago fuera de término",
            monto_neto=Decimal("5000.00"),
            alicuota_iva=Decimal("21.00"),
            tributos_adicionales=[
                {
                    "afip_tributo_id": 2,
                    "descripcion": "Percepción IIBB ARBA (3.5%)",
                    "base_imponible": Decimal("5000.00"),
                    "alicuota": Decimal("3.50"),
                    "importe": Decimal("175.00"),
                    "impuesto": imp_percep_iibb,
                }
            ]
        )

        self.assertIsNotNone(nd)
        self.assertEqual(nd.tipo, "nota_debito_cliente")
        self.assertEqual(nd.tipo_comprobante_afip, tipo_nd_a)
        self.assertEqual(nd.comprobante_asociado, factura)
        self.assertEqual(nd.monto_neto, Decimal("5000.00"))
        self.assertEqual(nd.monto_impuestos, Decimal("1050.00"))
        self.assertEqual(nd.monto_tributos, Decimal("175.00"))
        self.assertEqual(nd.monto_total, Decimal("6225.00"))

        nd.estado = "publicado"
        nd.afip_cae = "88990011223344"
        nd.save()

        # 2. Validar contabilización automática
        asiento = ContabilizacionDocumentoService.contabilizar_factura(nd)
        self.assertIsNotNone(asiento)
        self.assertEqual(asiento.estado, "asentado")

        apuntes = list(asiento.apuntes.all())
        total_debe = sum(a.debe for a in apuntes)
        total_haber = sum(a.haber for a in apuntes)
        self.assertEqual(total_debe, Decimal("6225.00"))
        self.assertEqual(total_haber, Decimal("6225.00"))

        # 3. Validar renderizado en el template fiscal
        report = ComprobanteFiscalPDFReport(nd)
        html = report.render()
        self.assertIn("NOTA DE DÉBITO", html)
        self.assertIn("0001-00000550", html)  # Comprobante asociado visible
        self.assertIn("Percepción IIBB ARBA (3.5%):", html)
        self.assertIn("175.00", html)
        self.assertIn("6225.00", html)

    def test_convenio_multilateral_coeficientes_report(self):
        """
        Valida que el reporte de Convenio Multilateral (CM05):
        1. Atribuya correctamente los ingresos y gastos por provincia/jurisdicción según SIFERE.
        2. Calcule los coeficientes de ingresos, coeficientes de gastos y el coeficiente unificado (Art. 2 CM).
        3. Cuadre la sumatoria total país en 100%.
        """
        from apps.contabilidad.reports.convenio_multilateral_report import ConvenioMultilateralCoeficientesReport

        # Cliente de Córdoba (904)
        cli_cba = Contacto.objects.create(
            codigo="CLI-CBA", nombre="CALZADOS CORDOBA S.R.L.", cuil="30444444449", provincia="Córdoba", condicion_iva="responsable_inscripto"
        )
        # Cliente de CABA (901)
        cli_caba = Contacto.objects.create(
            codigo="CLI-CABA", nombre="PALERMO SHOES S.A.", cuil="30666666668", provincia="CABA", condicion_iva="responsable_inscripto"
        )
        # Proveedor de Buenos Aires (902)
        prv_pba = Contacto.objects.create(
            codigo="PRV-PBA", nombre="CURTIEMBRE LANUS", cuil="30111111115", provincia="Buenos Aires", tipo="proveedor", condicion_iva="responsable_inscripto"
        )

        diario_v, _ = Diario.objects.get_or_create(codigo="VEN_CM", defaults={"nombre": "Ventas CM", "tipo": "ventas"})
        diario_c, _ = Diario.objects.get_or_create(codigo="COM_CM", defaults={"nombre": "Compras CM", "tipo": "compras"})

        # Venta 1: Córdoba $60,000 netos
        DocumentoDeuda.objects.create(
            diario=diario_v,
            tipo="factura_cliente",
            contacto=cli_cba,
            numero="0001-00000801",
            fecha_emision=timezone.now().date(),
            jurisdiccion_sifere="904",
            monto_neto=Decimal("60000.00"),
            monto_total=Decimal("72600.00"),
            estado="publicado",
        )

        # Venta 2: CABA $40,000 netos (Total ingresos país = $100,000 -> 60% Córdoba, 40% CABA)
        DocumentoDeuda.objects.create(
            diario=diario_v,
            tipo="factura_cliente",
            contacto=cli_caba,
            numero="0001-00000802",
            fecha_emision=timezone.now().date(),
            provincia_destino="CABA",
            monto_neto=Decimal("40000.00"),
            monto_total=Decimal("48400.00"),
            estado="publicado",
        )

        # Gasto 1: Buenos Aires $50,000 netos (Total gastos país = $50,000 -> 100% PBA)
        DocumentoDeuda.objects.create(
            diario=diario_c,
            tipo="factura_proveedor",
            contacto=prv_pba,
            numero="0005-00000901",
            fecha_emision=timezone.now().date(),
            jurisdiccion_sifere="902",
            monto_neto=Decimal("50000.00"),
            monto_total=Decimal("60500.00"),
            estado="publicado",
        )

        reporte = ConvenioMultilateralCoeficientesReport(periodo_anio=timezone.now().year)
        headers = reporte.get_headers()
        rows = reporte.get_rows()

        self.assertIn("Cód. SIFERE", headers)
        self.assertIn("Coeficiente Unificado CM05 (%)", headers)

        dict_rows = {r[0]: r for r in rows}

        # CABA (901): 40% ingresos, 0% gastos -> Coef Unificado = (40 + 0) / 2 = 20%
        row_caba = dict_rows["901"]
        self.assertEqual(row_caba[2], 40000.0)
        self.assertEqual(row_caba[3], 40.0)
        self.assertEqual(row_caba[4], 0.0)
        self.assertEqual(row_caba[6], 20.0)

        # PBA (902): 0% ingresos, 100% gastos -> Coef Unificado = (0 + 100) / 2 = 50%
        row_pba = dict_rows["902"]
        self.assertEqual(row_pba[2], 0.0)
        self.assertEqual(row_pba[4], 50000.0)
        self.assertEqual(row_pba[5], 100.0)
        self.assertEqual(row_pba[6], 50.0)

        # Córdoba (904): 60% ingresos, 0% gastos -> Coef Unificado = (60 + 0) / 2 = 30%
        row_cba = dict_rows["904"]
        self.assertEqual(row_cba[2], 60000.0)
        self.assertEqual(row_cba[3], 60.0)
        self.assertEqual(row_cba[6], 30.0)

        # Total País
        row_total = dict_rows["TOTAL"]
        self.assertEqual(row_total[2], 100000.0)
        self.assertEqual(row_total[4], 50000.0)
        self.assertEqual(row_total[6], 100.0)

    def test_convenio_multilateral_gastos_no_computables_y_cm03_alicuotas(self):
        """
        Valida que:
        1. Los gastos marcados como no computables (gasto_computable_convenio=False, Art. 3 CM) no distorsionen los coeficientes.
        2. Los impuestos de IIBB provinciales configurados en el modelo Impuesto sean tomados para la estimación del anticipo CM03.
        """
        diario_v, _ = Diario.objects.get_or_create(codigo="VEN_CM2", defaults={"nombre": "Ventas CM", "tipo": "ventas"})
        diario_c, _ = Diario.objects.get_or_create(codigo="COM_CM2", defaults={"nombre": "Compras CM", "tipo": "compras"})

        cli_sf = Contacto.objects.create(codigo="CLI-SF", nombre="CLIENTE SANTA FE", cuil="30712345678", provincia="Santa Fe")
        prv_cba = Contacto.objects.create(codigo="PRV-CBA", nombre="PROVEEDOR CBA", cuil="30787654321", provincia="Córdoba")

        # Configurar Impuesto de IIBB para Santa Fe (921) al 4.5%
        Impuesto.objects.create(
            nombre="IIBB Santa Fe",
            tipo="percepcion_iibb",
            aplicacion="ventas",
            alicuota=Decimal("4.50"),
            jurisdiccion_sifere="921",
            activo=True,
        )

        # 1. Venta en Santa Fe por $100,000 netos
        DocumentoDeuda.objects.create(
            diario=diario_v,
            tipo="factura_cliente",
            contacto=cli_sf,
            numero="0001-00009901",
            fecha_emision=timezone.now().date(),
            jurisdiccion_sifere="921",
            provincia_destino="Santa Fe",
            monto_neto=Decimal("100000.00"),
            monto_total=Decimal("121000.00"),
            estado="publicado",
        )

        # 2. Gasto computable en Córdoba por $20,000 netos (materia prima cuero)
        DocumentoDeuda.objects.create(
            diario=diario_c,
            tipo="factura_proveedor",
            contacto=prv_cba,
            numero="0002-00009902",
            fecha_emision=timezone.now().date(),
            jurisdiccion_sifere="904",
            monto_neto=Decimal("20000.00"),
            monto_total=Decimal("24200.00"),
            gasto_computable_convenio=True,
            estado="publicado",
        )

        # 3. Gasto NO computable en Córdoba por $80,000 netos (compra de maquinaria/bien de uso Art. 3 CM)
        DocumentoDeuda.objects.create(
            diario=diario_c,
            tipo="factura_proveedor",
            contacto=prv_cba,
            numero="0002-00009903",
            fecha_emision=timezone.now().date(),
            jurisdiccion_sifere="904",
            monto_neto=Decimal("80000.00"),
            monto_total=Decimal("96800.00"),
            gasto_computable_convenio=False,  # NO COMPUTABLE
            estado="publicado",
        )

        reporte = ConvenioMultilateralCoeficientesReport(
            periodo_anio=timezone.now().year,
            alicuota_default_cm03=Decimal("3.00"),
        )
        headers = reporte.get_headers()
        rows = reporte.get_rows()
        dict_rows = {r[0]: r for r in rows}

        self.assertIn("Base Imponible Atribuida ($)", headers)
        self.assertIn("Alícuota IIBB Actividad (%)", headers)
        self.assertIn("Impuesto Determinado Estimado CM03 ($)", headers)

        # Gasto total computable país debe ser solo $20,000 (el de $80,000 de bien de uso se excluyó)
        row_total = dict_rows["TOTAL"]
        self.assertEqual(row_total[4], 20000.0)

        # Santa Fe (921): 100% ingresos ($100,000), 0% gastos -> Coef CM05 = (100 + 0) / 2 = 50%
        # Base atribuida = $100,000 * 50% = $50,000.
        # Alícuota Santa Fe configurada en Impuesto = 4.5%
        # Impuesto CM03 estimado = $50,000 * 4.5% = $2,250.
        row_sf = dict_rows["921"]
        self.assertEqual(row_sf[2], 100000.0)
        self.assertEqual(row_sf[3], 100.0)
        self.assertEqual(row_sf[4], 0.0)
        self.assertEqual(row_sf[6], 50.0)       # Coef Unificado
        self.assertEqual(row_sf[7], 50000.0)    # Base Atribuida
        self.assertEqual(row_sf[8], 4.5)        # Alícuota
        self.assertEqual(row_sf[9], 2250.0)     # Impuesto Estimado CM03

        # Córdoba (904): 0% ingresos, 100% gastos computables ($20,000) -> Coef CM05 = (0 + 100) / 2 = 50%
        # Base atribuida = $100,000 * 50% = $50,000.
        # Alícuota por defecto = 3.0%
        # Impuesto CM03 estimado = $50,000 * 3.0% = $1,500.
        row_cba = dict_rows["904"]
        self.assertEqual(row_cba[4], 20000.0)
        self.assertEqual(row_cba[5], 100.0)
        self.assertEqual(row_cba[6], 50.0)
        self.assertEqual(row_cba[7], 50000.0)
        self.assertEqual(row_cba[8], 3.0)
        self.assertEqual(row_cba[9], 1500.0)












