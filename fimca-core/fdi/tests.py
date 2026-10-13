from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from apps.contactos.models import Contacto
from apps.eop.models import ContratoEOP, EOPHitoEscrow
from apps.mes.models import (
    EvaluacionTrayectoriaSETP,
    CertificadoDiligenciaDebida,
    PeritajeCalidadINTI,
)
from apps.mes.services import (
    SETPService,
    DiligenciaDebidaService,
    PeritajeCalidadService,
    AuditoriaCostosINTIService,
)


class MESFase2GobernanzaTestCase(TestCase):
    def setUp(self):
        self.taller = Contacto.objects.create(
            nombre="Taller Textil S.A.",
            cuil="20345678901",
            es_taller=True,
        )
        self.marca = Contacto.objects.create(
            nombre="Marca Comitente S.R.L.",
            cuil="30789012345",
            es_cliente=True,
        )
        self.contrato = ContratoEOP.objects.create(
            costo_mod=Decimal("1500.00"),
            costo_bom=Decimal("4000.00"),
            nodo_mes="https://mes.fimca.org",
        )
        self.hito_rcf = EOPHitoEscrow.objects.create(
            contrato=self.contrato,
            nombre="Hito Final RCF",
            porcentaje_tramo=Decimal("20.00"),
            requiere_auditoria_ptf=True,
            requiere_verificacion_arca=True,
        )

    def test_setp_arranque_en_frio_y_penalizacion_jit(self):
        """
        Verifica el régimen de arranque en frío (cupo 5000 UCI) y la deducción
        de 1.5 puntos por día de mora JIT en la marca comitente.
        """
        # 1. Inicialización en arranque en frío
        perfil_taller = SETPService.obtener_o_crear_perfil(self.taller.cuil, tipo_actor="taller")
        self.assertTrue(perfil_taller.es_arranque_en_frio)
        self.assertEqual(perfil_taller.cupo_operativo_uci, Decimal("5000.00"))
        self.assertEqual(perfil_taller.score_setp, Decimal("70.00"))
        self.assertEqual(perfil_taller.categoria_setp, "B")

        # 2. Marca comitente incurre en 10 días de demora JIT
        perfil_marca = SETPService.registrar_demora_comitente(
            cuit_comitente=self.marca.cuil, dias_demora=10
        )
        # 10 días * 1.5 = 15 puntos de penalización. Indice puntualidad: 100 - 15 = 85.00
        self.assertEqual(perfil_marca.indice_puntualidad_jit, Decimal("85.00"))
        self.assertEqual(perfil_marca.dias_mora_historicos_acumulados, 10)
        # Score ponderado: (85 * 0.5) + (100 * 0.5) = 42.5 + 50 = 92.5
        self.assertEqual(perfil_marca.score_setp, Decimal("92.50"))
        self.assertEqual(perfil_marca.categoria_setp, "A+")
        self.assertFalse(perfil_marca.es_arranque_en_frio)

    def test_certificado_diligencia_debida_safe_harbor(self):
        """
        Verifica la emisión de CDD-P (provisorio en mes 1) y CDD definitivo (>12 meses),
        constatando la vigencia del Puerto Seguro Laboral del Art. 30 LCT.
        """
        # 1. Cumplimiento de recaudos en mes 6 (CDD-P)
        cdd_provisorio = DiligenciaDebidaService.emitir_o_actualizar_cdd(
            tallerista=self.taller,
            comitente=self.marca,
            eop=self.contrato,
            periodo_mes_anio="2026-10",
            f931_presentado=True,
            dotacion=10,
            poliza_art=True,
            bancarizacion_sipa=True,
            situacion_arca_regular=True,
            meses_antiguedad_taller=6,
        )
        self.assertEqual(cdd_provisorio.tipo, "cdd_provisorio")
        self.assertEqual(cdd_provisorio.estado_puerto_seguro, "vigente")
        self.assertTrue(bool(cdd_provisorio.hash_verificacion_cdd))

        # 2. Defección en pago de ART en mes 14 -> Safe Harbor suspendido
        cdd_definitivo = DiligenciaDebidaService.emitir_o_actualizar_cdd(
            tallerista=self.taller,
            comitente=self.marca,
            eop=self.contrato,
            periodo_mes_anio="2026-11",
            f931_presentado=True,
            dotacion=10,
            poliza_art=False, # Falta pago ART
            bancarizacion_sipa=True,
            situacion_arca_regular=True,
            meses_antiguedad_taller=14,
        )
        self.assertEqual(cdd_definitivo.tipo, "cdd_definitivo")
        self.assertEqual(cdd_definitivo.estado_puerto_seguro, "suspendido")

    def test_peritaje_calidad_inti_suspension_rcf(self):
        """
        Verifica que una objeción de calidad suspenda el RCF y que el dictamen
        técnico pericial del INTI destrabe la liberación o confirme la merma.
        """
        # 1. Iniciar objeción
        peritaje = PeritajeCalidadService.iniciar_objecion_calidad(
            eop=self.contrato,
            comitente=self.marca,
            tallerista=self.taller,
            descripcion_objecion="Desvío en tolerancia de costura de cintura s/curva talle 42",
        )
        self.assertEqual(peritaje.estado, "iniciado")
        self.hito_rcf.refresh_from_db()
        self.assertEqual(self.hito_rcf.estado, "retencion_cierre_fiscal")

        # 2. Dictamen INTI desestimando la objeción (defecto NO imputable al taller)
        self.hito_rcf.factura_asociada_arca = "CAE-1234567890"
        self.hito_rcf.save()

        PeritajeCalidadService.dictaminar_peritaje_inti(
            peritaje_id=peritaje.id,
            dictamen_texto="Peritaje INTI N° 849/2026: Costura dentro del rango técnico admisible s/IRAM.",
            defecto_imputable_taller=False,
        )
        peritaje.refresh_from_db()
        self.assertEqual(peritaje.estado, "laudado_conforme")
        self.hito_rcf.refresh_from_db()
        self.assertEqual(self.hito_rcf.estado, "liberado")

    def test_alerta_temprana_costos_sub_paritarios(self):
        """
        Verifica que una tarifa por debajo del piso de convenio emita alerta temprana
        con pérdida de Puerto Seguro y sin detener el desembolso operativo al tallerista.
        """
        piso_convenio = Decimal("2500.00")
        tarifa_acordada = Decimal("1800.00")

        resultado = AuditoriaCostosINTIService.auditar_tarifa_etapa(
            tarifa_unitaria_ars=tarifa_acordada,
            piso_paritario_convenio_ars=piso_convenio,
        )
        self.assertTrue(resultado["inconsistencia_detectada"])
        self.assertEqual(resultado["alerta"], "ALERTA_TEMPRANA_COSTO_SUB_PARITARIO")
        self.assertFalse(resultado["suspende_desembolso_taller"])
        self.assertEqual(resultado["desvio_porcentual"], Decimal("28.00"))
