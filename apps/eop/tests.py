import json
from decimal import Decimal
import nacl.signing
from django.test import TestCase
from apps.base.models import ConfiguracionEmpresa
from apps.eop.models import ContratoEOP, EOPHitoEscrow
from apps.federacion.serializers import EntradaEOPSerializer


class ContratoEOPPayloadTestCase(TestCase):
    def setUp(self):
        self.empresa = ConfiguracionEmpresa.objects.create(
            razon_social="Marca Test S.A.",
            cuit="30712345678",
            condicion_iva="responsable_inscripto",
        )
        self.contrato = ContratoEOP.objects.create(
            costo_mod=Decimal("1000.00"),
            costo_cs=Decimal("200.00"),
            costo_bom=Decimal("500.00"),
            costo_fdi=Decimal("34.00"),
            costo_tax=Decimal("50.00"),
            costo_mg=Decimal("300.00"),
            nodo_mes="https://mes.fimca.org",
        )
        self.hito_1 = EOPHitoEscrow.objects.create(
            contrato=self.contrato,
            nombre="Hito Anticipo",
            porcentaje_tramo=Decimal("40.00"),
            requiere_auditoria_ptf=False,
        )
        self.hito_2 = EOPHitoEscrow.objects.create(
            contrato=self.contrato,
            nombre="Hito Final",
            porcentaje_tramo=Decimal("60.00"),
            requiere_auditoria_ptf=True,
        )

    def test_generar_payload_canonico_y_merkle_root(self):
        payload_str = self.contrato.generar_payload_canonico()
        payload = json.loads(payload_str)

        self.assertEqual(payload["protocolo_version"], "2.0")
        self.assertEqual(payload["comitente_cuit"], "30712345678")
        self.assertEqual(Decimal(payload["monto_total_uci"]), self.contrato.monto_total_uci)
        self.assertEqual(len(payload["cronograma_escrow_hitos"]), 2)
        self.assertEqual(payload["cronograma_escrow_hitos"][0]["porcentaje_tramo"], "40.00")
        self.assertEqual(payload["cronograma_escrow_hitos"][1]["porcentaje_tramo"], "60.00")
        self.assertTrue(bool(payload["merkle_root_bom"]))

    def test_serializador_federado_con_firma_ed25519(self):
        signing_key = nacl.signing.SigningKey.generate()
        verify_key = signing_key.verify_key
        clave_pub_hex = verify_key.encode().hex()

        payload_str = self.contrato.generar_payload_canonico()
        payload_dict = json.loads(payload_str)
        # Regla obligatoria: mínimo 2 etapas en el payload
        payload_dict["etapas_productivas"] = [
            {"orden": 1, "servicio": "Corte", "tallerista": {"cuit": "30689123452"}, "costo_servicio": "50.00"},
            {"orden": 2, "servicio": "Aparado", "tallerista": {"cuit": "20184930213"}, "costo_servicio": "50.00"},
        ]

        payload_bytes = json.dumps(payload_dict, separators=(",", ":"), sort_keys=True).encode("utf-8")
        firma_hex = signing_key.sign(payload_bytes).signature.hex()

        self.contrato.sellar_hash_seguridad()

        data_entrada = {
            "uuid_identificador": str(self.contrato.uuid_identificador),
            "hash_seguridad": self.contrato.hash_seguridad,
            "comitente_cuit": "30712345678",
            "tallerista_cuit": "20123456789",
            "monto_total_uci": str(self.contrato.monto_total_uci),
            "payload_canonico": payload_dict,
            "firma_comitente": firma_hex,
            "clave_publica_comitente": clave_pub_hex,
            "cronograma_escrow_hitos": payload_dict["cronograma_escrow_hitos"],
        }

        serializer = EntradaEOPSerializer(data=data_entrada)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_crear_contrato_desde_op_y_cotizacion_uci(self):
        from apps.eop.models import IndiceUCI
        from apps.eop.services import EOPService
        from apps.produccion.models import OrdenProduccion, OPEtapaTracking, RecetaEtapa
        from apps.inventario.models import ProductoTemplate
        import datetime

        # Fijar cotización UCI: 1 UCI = 500 ARS
        IndiceUCI.objects.create(
            fecha=datetime.date.today(),
            valor_ars=Decimal("500.00")
        )

        op = OrdenProduccion.objects.create(
            numero="OP-TEST-001",
            cantidad_total=100,
            tipo="interna",
        )

        # Regla obligatoria: Mínimo 2 etapas
        servicio_corte, _ = ProductoTemplate.objects.get_or_create(nombre="Corte", tipo="servicio")
        servicio_aparado, _ = ProductoTemplate.objects.get_or_create(nombre="Aparado", tipo="servicio")

        receta_etapa1 = RecetaEtapa.objects.create(servicio=servicio_corte, orden_ejecucion=1)
        receta_etapa2 = RecetaEtapa.objects.create(servicio=servicio_aparado, orden_ejecucion=2)

        OPEtapaTracking.objects.create(
            op=op,
            etapa_origen=receta_etapa1,
            costo_servicio_total=Decimal("25000.00") # 50 UCI
        )
        OPEtapaTracking.objects.create(
            op=op,
            etapa_origen=receta_etapa2,
            costo_servicio_total=Decimal("25000.00") # 50 UCI
        )

        contrato = EOPService.crear_contrato_desde_op(op)

        self.assertEqual(contrato.costo_mod, Decimal("100.00")) # 50.000 / 500 = 100 UCI
        self.assertEqual(contrato.orden_produccion_local, op)
        
        # Regla obligatoria: Hito Cero (anticipo) + 2 Hitos por Etapa (Corte y Aparado) = 3 hitos
        self.assertEqual(contrato.hitos.count(), 3)
        hitos = list(contrato.hitos.all().order_by("id"))
        self.assertTrue("Hito Cero" in hitos[0].nombre)
        self.assertTrue("Corte" in hitos[1].nombre)
        self.assertTrue("Aparado" in hitos[2].nombre)
        self.assertEqual(sum(h.porcentaje_tramo for h in hitos), Decimal("100.00"))

        payload = json.loads(contrato.generar_payload_canonico())
        self.assertEqual(payload["cotizacion_uci_ars"], "500.00")
        self.assertEqual(payload["vector_costos"]["mod_servicios"], "100.00")
        self.assertEqual(len(payload["etapas_productivas"]), 2)
        self.assertTrue("canon_fdi_mes" in payload["vector_costos"])
        self.assertTrue("insumos_bom" in payload["vector_costos"])
