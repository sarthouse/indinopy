import json
from decimal import Decimal
import nacl.signing
from django.test import TestCase
from apps.base.models import ConfiguracionEmpresa
from apps.eop.models import ContratoEOP, EOPHitoEscrow
from apps.eop.serializers import EntradaEOPSerializer


class ContratoEOPPayloadTestCase(TestCase):
    def setUp(self):
        self.empresa = ConfiguracionEmpresa.objects.create(
            razon_social="Marca Test S.A.",
            cuit="30712345678",
            condicion_iva="responsable_inscripto",
        )
        self.contrato = ContratoEOP.objects.create(
            costo_mod=Decimal("1000.00"),
            costo_bom=Decimal("500.00"),
            costo_fdi=Decimal("15.00"),
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
            "firma_tallerista": "mocked_tallerista_signature_hex",
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

    def test_parametros_fdi_service_fallback_y_cache(self):
        from apps.eop.services import ParametrosFDIService
        from django.core.cache import cache

        cache.delete(ParametrosFDIService.CACHE_KEY)

        # 1. Sin respuesta del servidor MES, debe devolver el fallback reglamentario (1.5%)
        alicuota = ParametrosFDIService.obtener_alicuota_recargo_fdi(mes_url="http://endpoint-inexistente:9999")
        self.assertEqual(alicuota, Decimal("0.015"))

        # 2. Con datos en caché, debe devolver el valor cacheado
        cache.set(ParametrosFDIService.CACHE_KEY, {"alicuota_total_recargo": "0.018"}, 60)
        alicuota_cache = ParametrosFDIService.obtener_alicuota_recargo_fdi()
        self.assertEqual(alicuota_cache, Decimal("0.018"))
        cache.delete(ParametrosFDIService.CACHE_KEY)

    def test_rechazo_eop_por_alicuota_desactualizada(self):
        signing_key = nacl.signing.SigningKey.generate()
        verify_key = signing_key.verify_key

        payload_str = self.contrato.generar_payload_canonico()
        payload_dict = json.loads(payload_str)
        payload_dict["etapas_productivas"] = [
            {"orden": 1, "servicio": "Corte", "tallerista": {"cuit": "30689123452"}, "costo_servicio": "50.00"},
            {"orden": 2, "servicio": "Aparado", "tallerista": {"cuit": "20184930213"}, "costo_servicio": "50.00"},
        ]

        # Alteramos el canon_fdi_mes a un valor desactualizado (ej: 5.00 en vez de 15.00 que es el 1.5% de 1000.00)
        payload_dict["vector_costos"]["canon_fdi_mes"] = "5.00"

        payload_bytes = json.dumps(payload_dict, separators=(",", ":"), sort_keys=True).encode("utf-8")
        firma_hex = signing_key.sign(payload_bytes).signature.hex()

        data_entrada = {
            "uuid_identificador": str(self.contrato.uuid_identificador),
            "hash_seguridad": self.contrato.hash_seguridad,
            "comitente_cuit": "30712345678",
            "tallerista_cuit": "20123456789",
            "monto_total_uci": str(self.contrato.monto_total_uci),
            "payload_canonico": payload_dict,
            "firma_comitente": firma_hex,
            "clave_publica_comitente": verify_key.encode().hex(),
            "firma_tallerista": "mocked_tallerista_signature_hex",
            "cronograma_escrow_hitos": payload_dict["cronograma_escrow_hitos"],
        }

        serializer = EntradaEOPSerializer(data=data_entrada)
        self.assertFalse(serializer.is_valid())
        self.assertIn("ALICUOTA_DESACTUALIZADA", str(serializer.errors))

    def test_calculo_vector_costos_sin_bom(self):
        """
        Verifica que el monto_total_uci excluya el costo_bom conforme al Art. 4° inc. 4.b,
        integrando exclusivamente MOD + FDI (operativo + stock).
        """
        contrato = ContratoEOP.objects.create(
            costo_mod=Decimal("2000.00"),
            costo_bom=Decimal("15000.00"),
            costo_fdi_operativo=Decimal("30.00"),
            costo_fdi_stock=Decimal("75.00"),
            nodo_mes="https://mes.fimca.org",
        )
        self.assertEqual(contrato.costo_fdi, Decimal("105.00"))
        # Deuda exigible = 2000 + 105 = 2105 (excluye 15000 de BOM)
        self.assertEqual(contrato.monto_total_uci, Decimal("2105.00"))
        self.assertEqual(contrato.valor_declarado_custodia_bom, Decimal("15000.00"))

    def test_logistica_jit_prorroga_y_standby(self):
        """
        Verifica el régimen JIT (Art. 5° bis): prórroga de vencimiento y cálculo de standby
        tras superar los 5 días de mora en abastecimiento de insumos.
        """
        import datetime
        from apps.eop.services import LogisticaJITService

        hoy = datetime.date.today()
        contrato = ContratoEOP.objects.create(
            costo_mod=Decimal("1000.00"),
            fecha_vencimiento_comercial=hoy + datetime.timedelta(days=60),
            nodo_mes="https://mes.fimca.org",
        )

        fecha_esperada = hoy - datetime.timedelta(days=10)
        # 10 días de demora: días_standby = 10 - 5 = 5 días
        incidencia = LogisticaJITService.registrar_demora_abastecimiento(
            contrato=contrato,
            etapa_afectada="Corte Inicial",
            fecha_esperada=fecha_esperada,
            fecha_real=hoy,
            smvm_vigente=Decimal("300000.00"),
        )

        self.assertIsNotNone(incidencia)
        self.assertEqual(incidencia.dias_demora, 10)
        # Standby: 5 días * (0.5 * 300000 / 30) = 5 * 5000 = 25000.00 ARS
        self.assertEqual(incidencia.compensacion_standby_devengada, Decimal("25000.00"))
        contrato.refresh_from_db()
        self.assertTrue(contrato.es_justo_a_tiempo)
        self.assertEqual(contrato.dias_mora_comitente_jit, 10)
        self.assertEqual(contrato.compensacion_standby_acumulada_ars, Decimal("25000.00"))
        self.assertEqual(
            contrato.fecha_vencimiento_recalculada,
            contrato.fecha_vencimiento_comercial + datetime.timedelta(days=10),
        )

    def test_rescision_taller_por_mora_jit(self):
        """
        Verifica la facultad rescisoria de pleno derecho del taller façonnier
        al acumular 15 o más días de mora de la comitente.
        """
        from apps.eop.services import LogisticaJITService

        contrato = ContratoEOP.objects.create(
            costo_mod=Decimal("1000.00"),
            dias_mora_comitente_jit=14,
            nodo_mes="https://mes.fimca.org",
        )
        with self.assertRaises(ValueError):
            LogisticaJITService.resolver_contrato_por_mora_taller(contrato)

        contrato.dias_mora_comitente_jit = 15
        contrato.save()
        resuelto = LogisticaJITService.resolver_contrato_por_mora_taller(contrato)
        self.assertTrue(resuelto)
        contrato.refresh_from_db()
        self.assertEqual(contrato.estado_escrow, "en_disputa")

    def test_liberacion_hito_cero_concurrencia(self):
        """
        Verifica que Hito Cero exija firma bilateral, remito oficial y póliza de stock activa.
        """
        from apps.eop.services import EOPService

        contrato = ContratoEOP.objects.create(
            costo_mod=Decimal("1000.00"),
            nodo_mes="https://mes.fimca.org",
        )
        hito_cero = EOPHitoEscrow.objects.create(
            contrato=contrato,
            nombre="Hito Cero - Anticipo",
            porcentaje_tramo=Decimal("35.00"),
            requiere_auditoria_ptf=False,
        )

        # 1. Falla por falta de firmas bilaterales
        with self.assertRaises(ValueError) as ctx:
            EOPService.liberar_hito(hito_cero.id, validar_concurrencia_h0=True)
        self.assertIn("firma bilateral", str(ctx.exception))

        # 2. Agregar firmas pero sin remito oficial
        contrato.firmas_digitales = {
            "comitente": {"firma_hex": "comitente123"},
            "tallerista": {"firma_hex": "tallerista123"},
        }
        contrato.save()
        with self.assertRaises(ValueError) as ctx:
            EOPService.liberar_hito(hito_cero.id, validar_concurrencia_h0=True)
        self.assertIn("remito oficial", str(ctx.exception))

        # 3. Agregar remito pero sin seguro verificado
        hito_cero.remito_oficial_uuid = "REM-OFICIAL-999"
        hito_cero.save()
        with self.assertRaises(ValueError) as ctx:
            EOPService.liberar_hito(hito_cero.id, validar_concurrencia_h0=True)
        self.assertIn("seguro de stock", str(ctx.exception))

        # 4. Cumpliendo todos los recaudos copulativos se libera
        hito_cero.seguro_stock_verificado = True
        hito_cero.save()
        EOPService.liberar_hito(hito_cero.id, validar_concurrencia_h0=True)
        hito_cero.refresh_from_db()
        self.assertEqual(hito_cero.estado, "liberado")

    def test_rcf_timelock_badlar(self):
        """
        Verifica que el Hito Final retenga fondos en retencion_cierre_fiscal y devengue
        mora BADLAR tras expirar la ventana total de gracia (21 días).
        """
        import datetime
        from django.utils import timezone
        from apps.eop.services import EOPService, RCFService

        contrato = ContratoEOP.objects.create(
            costo_mod=Decimal("10000.00"),
            nodo_mes="https://mes.fimca.org",
        )
        hito_final = EOPHitoEscrow.objects.create(
            contrato=contrato,
            nombre="Hito Final - Cierre Fiscal",
            porcentaje_tramo=Decimal("20.00"), # 2000 UCI
            requiere_auditoria_ptf=False,
            requiere_verificacion_arca=True,
        )

        EOPService.liberar_hito(hito_final.id)
        hito_final.refresh_from_db()
        self.assertEqual(hito_final.estado, "retencion_cierre_fiscal")
        self.assertIsNotNone(hito_final.fecha_entrega_lote_conforme)

        # Simular que transcurrieron 31 días desde la entrega (10 días de mora más allá de los 21 de gracia)
        hito_final.fecha_entrega_lote_conforme = timezone.now() - datetime.timedelta(days=31)
        hito_final.save()

        interes = RCFService.auditar_timelock_rcf(
            hito_id=hito_final.id,
            tasa_badlar_anual=Decimal("0.365"), # 36.5% anual -> 0.1% diario
        )
        # Monto tramo = 2000. Tasa diaria = 0.001. Días mora = 10. Interés = 2000 * 0.001 * 10 = 20.00
        self.assertEqual(interes, Decimal("20.00"))
        hito_final.refresh_from_db()
        self.assertEqual(hito_final.cargo_mora_badlar_devengado, Decimal("20.00"))

