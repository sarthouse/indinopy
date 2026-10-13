from decimal import Decimal
from rest_framework import serializers

from .models import (
    CarteraTitulizableBIP,
    SerieBonoBIP,
    SubcuentaReservaFondo,
    PolizaColectivaStock,
    EvaluacionTrayectoriaSETP,
    CertificadoDiligenciaDebida,
    PautaEscrowMES,
)


# =====================================================================
# SERIALIZERS — GOBERNANZA, SETP Y DILIGENCIA DEBIDA
# =====================================================================

class SETPMiCalificacionSerializer(serializers.ModelSerializer):
    """
    Serializer de salida para el endpoint de Habeas Data y Scoring SETP (Art. 16° Ley e-OP).
    """
    cuit = serializers.CharField(source="cuit_evaluado")
    metricas = serializers.SerializerMethodField()

    class Meta:
        model = EvaluacionTrayectoriaSETP
        fields = [
            "cuit",
            "tipo_actor",
            "score_setp",
            "categoria_setp",
            "es_arranque_en_frio",
            "cupo_operativo_uci",
            "metricas",
        ]

    def get_metricas(self, obj):
        return {
            "indice_cumplimiento_plazos": str(obj.indice_cumplimiento_plazos),
            "indice_calidad_tecnica": str(obj.indice_calidad_tecnica),
            "ops_cumplidas_exitosas": obj.ops_cumplidas_exitosas,
            "indice_puntualidad_jit": str(obj.indice_puntualidad_jit),
            "indice_pago_vencimientos": str(obj.indice_pago_vencimientos),
            "dias_mora_historicos_acumulados": obj.dias_mora_historicos_acumulados,
        }


class EstadoCreditoFDISerializer(serializers.ModelSerializer):
    """
    Serializer de respuesta para la consulta de estado de crédito de una marca comitente.
    """
    cuit_marca = serializers.CharField(source="cuit_evaluado")
    dias_mora_acumulados = serializers.IntegerField(source="dias_mora_historicos_acumulados")
    bloqueo_por_mora = serializers.SerializerMethodField()

    class Meta:
        model = EvaluacionTrayectoriaSETP
        fields = [
            "cuit_marca",
            "score_setp",
            "categoria_setp",
            "es_arranque_en_frio",
            "cupo_operativo_uci",
            "dias_mora_acumulados",
            "bloqueo_por_mora",
        ]

    def get_bloqueo_por_mora(self, obj):
        return obj.dias_mora_historicos_acumulados > 15


class CertificadoDiligenciaDebidaSerializer(serializers.ModelSerializer):
    """
    Serializer para constatación pública del Certificado de Diligencia Debida (CDD).
    """
    eop_uuid = serializers.UUIDField(source="eop_asociada.uuid_identificador", read_only=True)
    taller_cuit = serializers.CharField(source="tallerista.cuil", read_only=True, default="")
    comitente_cuit = serializers.CharField(source="comitente.cuil", read_only=True, default="")
    periodo = serializers.CharField(source="periodo_mes_anio")
    recaudos = serializers.SerializerMethodField()

    class Meta:
        model = CertificadoDiligenciaDebida
        fields = [
            "eop_uuid",
            "taller_cuit",
            "comitente_cuit",
            "periodo",
            "tipo",
            "estado_puerto_seguro",
            "hash_verificacion_cdd",
            "recaudos",
        ]

    def get_recaudos(self, obj):
        return {
            "f931_presentado": obj.f931_presentado,
            "dotacion_declarada": obj.dotacion_declarada,
            "poliza_art_vigente": obj.poliza_art_vigente,
            "bancarizacion_salarios_verificada": obj.bancarizacion_salarios_verificada,
            "situacion_fiscal_arca_regular": obj.situacion_fiscal_arca_regular,
        }


class ParametrosArancelariosSerializer(serializers.Serializer):
    """
    Serializer para publicar parámetros arancelarios y alícuotas del FDI.
    """
    version_arancel = serializers.CharField()
    alicuota_canon_mes = serializers.CharField()
    alicuota_fondo_riesgo_fdi = serializers.CharField()
    alicuota_total_recargo = serializers.CharField()
    alicuota_stock = serializers.CharField()
    descripcion = serializers.CharField()


# =====================================================================
# SERIALIZERS — MERCADO DE CAPITALES, TITULIZACIÓN Y RESERVAS FDI
# =====================================================================

class CarteraTitulizableBIPSerializer(serializers.ModelSerializer):
    """
    Serializer de lectura para Carteras Titulizables de e-OPs (Art. 17° Ley e-OP).
    """
    cantidad_eops = serializers.SerializerMethodField()

    class Meta:
        model = CarteraTitulizableBIP
        fields = [
            "id",
            "codigo_cartera",
            "descripcion",
            "monto_nominal_total_ars",
            "monto_nominal_total_uci",
            "calificacion_promedio_setp",
            "cantidad_eops",
            "estado",
            "fecha_corte",
        ]

    def get_cantidad_eops(self, obj):
        return obj.contratos.count()


class ConformarCarteraBIPInputSerializer(serializers.Serializer):
    """
    Serializer de validación de entrada para conformar una nueva Cartera BIP.
    """
    codigo_cartera = serializers.CharField(max_length=64, trim_whitespace=True)
    eop_uuids = serializers.ListField(
        child=serializers.UUIDField(),
        allow_empty=False,
        help_text="Lista de UUIDs de contratos e-OP a empaquetar.",
    )
    descripcion = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")

    def validate_codigo_cartera(self, value):
        val = value.strip().upper()
        if CarteraTitulizableBIP.objects.filter(codigo_cartera=val).exists():
            raise serializers.ValidationError(f"Ya existe una cartera con el código '{val}'.")
        return val


class SerieBonoBIPSerializer(serializers.ModelSerializer):
    """
    Serializer de lectura para Series de Bonos de Inversión Productiva (BIP).
    """
    ticker = serializers.CharField(source="codigo_ticker")
    cartera = serializers.CharField(source="cartera_subyacente.codigo_cartera", read_only=True)
    tasa_tna = serializers.DecimalField(source="tasa_interes_anual", max_digits=5, decimal_places=2)
    etiqueta_svs = serializers.BooleanField(source="es_etiqueta_svs")
    hash_prospecto = serializers.CharField(source="hash_seguridad_prospecto")

    class Meta:
        model = SerieBonoBIP
        fields = [
            "ticker",
            "cartera",
            "numero_serie",
            "plazo_dias",
            "moneda",
            "monto_emision_nominal",
            "tasa_tna",
            "fecha_emision",
            "fecha_vencimiento",
            "etiqueta_svs",
            "revisor_externo_cnv",
            "hash_prospecto",
            "estado",
        ]


class EmitirBonoBIPInputSerializer(serializers.Serializer):
    """
    Serializer de validación de entrada para emitir una Serie de Bono BIP sobre cartera.
    """
    cartera_id = serializers.IntegerField(min_value=1)
    codigo_ticker = serializers.CharField(max_length=20, trim_whitespace=True)
    plazo_dias = serializers.ChoiceField(
        choices=[60, 90, 120, 180, 360],
        default=90,
        help_text="Plazo en días autorizado por el régimen CNV RG 917/2021.",
    )
    moneda = serializers.ChoiceField(
        choices=[("uci", "UCI"), ("ars", "ARS"), ("usd", "USD")],
        default="uci",
    )
    tasa_interes_anual = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        min_value=Decimal("0.00"),
    )
    revisor_externo_cnv = serializers.CharField(
        max_length=150,
        required=False,
        default="Calificadora de Riesgo SVS / CNV",
    )

    def validate_codigo_ticker(self, value):
        val = value.strip().upper()
        if SerieBonoBIP.objects.filter(codigo_ticker=val).exists():
            raise serializers.ValidationError(f"El ticker '{val}' ya fue emitido y se encuentra registrado.")
        return val


class SubcuentaReservaFondoSerializer(serializers.ModelSerializer):
    """
    Serializer de lectura para las 4 Subcuentas Estatutarias del Fondo (Art. 16° Ley e-OP).
    """
    etiqueta = serializers.CharField(source="get_tipo_reserva_display", read_only=True)

    class Meta:
        model = SubcuentaReservaFondo
        fields = [
            "tipo_reserva",
            "etiqueta",
            "descripcion",
            "saldo_disponible_ars",
            "saldo_bloqueado_ars",
            "alicuota_canon_pct",
        ]


class PolizaColectivaStockSerializer(serializers.ModelSerializer):
    """
    Serializer de lectura para la Póliza Colectiva de Stock en Custodia (Art. 20° bis Ley e-OP).
    """
    cobertura_activa = serializers.BooleanField(source="activa", read_only=True)
    vigencia_desde = serializers.DateTimeField(source="fecha_vigencia_desde", format="%Y-%m-%dT%H:%M:%S")
    vigencia_hasta = serializers.DateTimeField(source="fecha_vigencia_hasta", format="%Y-%m-%dT%H:%M:%S")

    class Meta:
        model = PolizaColectivaStock
        fields = [
            "cobertura_activa",
            "numero_poliza",
            "compania_aseguradora",
            "vigencia_desde",
            "vigencia_hasta",
            "monto_maximo_cobertura_ars",
            "tasa_prima_anual_pct",
        ]
