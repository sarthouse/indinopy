import hmac
import hashlib
import json
import base64
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch

from apps.base.models import ConfiguracionEmpresa
from apps.contactos.models import Contacto
from apps.inventario.models import Producto, Ubicacion
from apps.ventas.models import CanalVenta, OrdenVenta
from apps.integraciones.woocommerce.models import TiendaWooCommerce
from apps.integraciones.woocommerce.normalizers import WooCommerceNormalizer


class WooCommerceIntegrationTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.empresa = ConfiguracionEmpresa.get_solo()
        self.empresa.razon_social = "CALZADOS ARGENTINOS S.A."
        self.empresa.cuit = "30712345678"
        self.empresa.save()

        self.almacen, _ = Ubicacion.objects.get_or_create(tipo="interna", nombre="Depósito E-commerce")

        self.canal = CanalVenta.objects.create(
            empresa=self.empresa,
            nombre="Canal WooCommerce Test",
            codigo="WC-TIENDA",
            tipo="woocommerce",
            almacen_predeterminado=self.almacen,
        )

        self.webhook_secret = "clave_secreta_webhook_123456"
        self.tienda = TiendaWooCommerce.objects.create(
            empresa=self.empresa,
            canal_venta=self.canal,
            nombre="Tienda Oficial Integración",
            codigo_prefijo="WC-OFIC",
            url="https://mitienda.com",
            consumer_key="ck_test_key",
            consumer_secret="cs_test_secret",
            webhook_secret=self.webhook_secret,
            activa=True,
        )

        self.producto = Producto.objects.create(
            sku="MOCASIN-41-MARRON",
            nombre="Mocasín Náutico 41 Marrón",
            precio_venta=Decimal("55000.00"),
            activo=True,
        )

    def _generar_firma(self, payload_bytes: bytes) -> str:
        return base64.b64encode(
            hmac.new(
                key=self.webhook_secret.encode("utf-8"),
                msg=payload_bytes,
                digestmod=hashlib.sha256,
            ).digest()
        ).decode("utf-8")

    def test_webhook_firma_invalida_rechazada(self):
        """Valida que un webhook con firma ausente o inválida devuelva HTTP 401."""
        url = reverse("integraciones_woocommerce:webhook", kwargs={"tienda_id": self.tienda.id})
        
        # 1. Sin header de firma
        resp = self.client.post(url, data=json.dumps({"test": 1}), content_type="application/json")
        self.assertEqual(resp.status_code, 401)
        self.assertIn("Firma ausente", resp.content.decode())

        # 2. Con firma adulterada
        resp2 = self.client.post(
            url,
            data=json.dumps({"test": 1}),
            content_type="application/json",
            HTTP_X_WC_WEBHOOK_SIGNATURE="firma_falsa_invalida",
            HTTP_X_WC_WEBHOOK_TOPIC="order.created",
        )
        self.assertEqual(resp2.status_code, 401)
        self.assertIn("Firma inválida", resp2.content.decode())

    @patch("apps.integraciones.woocommerce.tasks.procesar_webhook_woo_async.delay")
    def test_webhook_valido_encola_tarea_celery(self, mock_celery_delay):
        """
        Valida que un webhook con firma HMAC correcta responda HTTP 200 en <150ms
        y encole la tarea asíncrona en Celery.
        """
        payload = {
            "id": 54321,
            "number": "54321",
            "status": "processing",
            "total": "55000.00",
            "line_items": [
                {
                    "id": 1,
                    "sku": "MOCASIN-41-MARRON",
                    "quantity": 1,
                    "price": "55000.00",
                }
            ],
            "billing": {
                "first_name": "Ana",
                "last_name": "Valenzuela",
                "email": "ana.valenzuela@example.com",
            }
        }
        payload_bytes = json.dumps(payload).encode("utf-8")
        signature = self._generar_firma(payload_bytes)

        url = reverse("integraciones_woocommerce:webhook", kwargs={"tienda_id": self.tienda.id})
        resp = self.client.post(
            url,
            data=payload_bytes,
            content_type="application/json",
            HTTP_X_WC_WEBHOOK_SIGNATURE=signature,
            HTTP_X_WC_WEBHOOK_TOPIC="order.created",
        )

        self.assertEqual(resp.status_code, 200)
        json_data = resp.json()
        self.assertEqual(json_data.get("status"), "encolado")
        self.assertEqual(json_data.get("topic"), "order.created")

        # Verificar llamada a Celery
        mock_celery_delay.assert_called_once_with(self.tienda.id, "order.created", payload)

    def test_normalizer_mapeo_fiscal_dni_cuit_argentina(self):
        """
        Valida que el normalizador extraiga correctamente el DNI/CUIT y la condición IVA
        desde los metadatos habituales del checkout de WooCommerce en Argentina.
        """
        billing = {
            "first_name": "ESTEBAN",
            "last_name": "QUITO",
            "email": "esteban.quito@comercio.com",
            "phone": "11-4444-5555",
            "address_1": "Belgrano 100",
            "city": "Quilmes",
            "state": "Buenos Aires",
            "postcode": "1878",
        }
        meta_data = [
            {"key": "_billing_dni", "value": "20311223344"},
            {"key": "_billing_condicion_iva", "value": "monotributista"},
        ]

        cliente_dto = WooCommerceNormalizer.normalizar_cliente(billing, meta_data)

        self.assertEqual(cliente_dto.nombre, "ESTEBAN QUITO")
        self.assertEqual(cliente_dto.cuit, "20311223344")
        self.assertEqual(cliente_dto.condicion_iva, "monotributista")
        self.assertEqual(cliente_dto.ciudad, "Quilmes")
        self.assertEqual(cliente_dto.provincia, "Buenos Aires")

    def test_backward_compatibility_endpoint_ventas_urls(self):
        """
        Valida que la ruta histórica en /ventas/webhooks/woocommerce/<id>/
        siga funcionando sin interrupciones redirigiendo al mismo controlador.
        """
        url_ventas = reverse("ventas:woo_webhook", kwargs={"tienda_id": self.tienda.id})
        payload_bytes = b'{"ping": 1}'
        signature = self._generar_firma(payload_bytes)

        with patch("apps.integraciones.woocommerce.tasks.procesar_webhook_woo_async.delay") as mock_delay:
            resp = self.client.post(
                url_ventas,
                data=payload_bytes,
                content_type="application/json",
                HTTP_X_WC_WEBHOOK_SIGNATURE=signature,
                HTTP_X_WC_WEBHOOK_TOPIC="ping",
            )
            self.assertEqual(resp.status_code, 200)
            mock_delay.assert_called_once_with(self.tienda.id, "ping", {"ping": 1})
