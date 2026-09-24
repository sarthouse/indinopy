from decimal import Decimal
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from apps.base.models import ConfiguracionEmpresa, Moneda
from apps.contactos.models import Contacto
from apps.inventario.models import ProductoTemplate, Producto, UnidadMedida, Ubicacion
from apps.produccion.models import (
    OrdenProduccion,
    Receta,
    RecetaEtapa,
    OPEtapaTracking,
)
from apps.produccion.services import ProduccionService
from apps.eop.models import ContratoEOP


class ValidacionFirmaTalleristaOPTestCase(TestCase):
    def setUp(self):
        self.empresa = ConfiguracionEmpresa.get_solo()
        self.empresa.razon_social = "CALZADOS INDUSTRIALES S.A."
        self.empresa.cuit = "30712345678"
        self.empresa.save()

        self.uom = UnidadMedida.objects.create(nombre="Par", simbolo="PR", tipo="unidad")
        self.template = ProductoTemplate.objects.create(
            nombre="Bota Táctica", unidad_medida=self.uom, precio=Decimal("50000.00")
        )
        self.producto = Producto.objects.create(
            template=self.template, sku="BOTA-TAC-42", precio_extra=Decimal("0.00")
        )

        self.tallerista = Contacto.objects.create(
            nombre="Taller El Aparado",
            razon_social="Taller El Aparado SRL",
            cuil="20301112223",
            es_proveedor=True,
        )

        self.receta = Receta.objects.create(
            producto_template=self.template, nombre_version="V1"
        )
        self.etapa_receta = RecetaEtapa.objects.create(
            receta=self.receta,
            orden_ejecucion=1,
            duracion_estimada_horas=8,
        )

        self.op = OrdenProduccion.objects.create(
            numero="OP-TEST-001",
            receta=self.receta,
            cantidad_total=100,
            tipo="fason",
            estado="borrador",
        )
        self.etapa_tracking = OPEtapaTracking.objects.create(
            op=self.op,
            etapa_origen=self.etapa_receta,
            tallerista_asignado=self.tallerista,
            estado="pendiente",
        )

    def test_bloqueo_confirmacion_op_sin_firma_tallerista(self):
        """
        Una OP federada o a fasón no puede pasar a 'confirmado'
        si el tallerista gestor no estampó su firma en el contrato e-OP.
        """
        # Asociamos contrato e-OP sin firma
        contrato = ContratoEOP.objects.create(
            orden_produccion_local=self.op,
            costo_mod=Decimal("1000.00"),
            nodo_mes="https://mes.fimca.org",
            firmas_digitales={},
        )

        with self.assertRaises(ValidationError) as cm:
            ProduccionService.confirmar_op(self.op)

        self.assertIn("aún no ha firmado digitalmente el contrato e-OP", str(cm.exception))
        self.op.refresh_from_db()
        self.assertEqual(self.op.estado, "borrador")

    def test_confirmacion_exitosa_con_firma_tallerista(self):
        """
        Cuando el tallerista firma el contrato e-OP, la OP se confirma correctamente.
        """
        contrato = ContratoEOP.objects.create(
            orden_produccion_local=self.op,
            costo_mod=Decimal("1000.00"),
            nodo_mes="https://mes.fimca.org",
            firmas_digitales={
                "tallerista": {
                    "cuit": "20301112223",
                    "firma_hex": "ab1234cd5678ef90",
                    "timestamp": timezone.now().isoformat(),
                }
            },
        )

        ProduccionService.confirmar_op(self.op)
        self.op.refresh_from_db()
        self.assertEqual(self.op.estado, "confirmado")
