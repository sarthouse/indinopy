from datetime import date
from decimal import Decimal
from typing import Any, List, Optional
from django.db.models import Sum, Q

from apps.base.reports.base import BaseTabularReport
from apps.contabilidad.models import DocumentoDeuda


# Tabla oficial de Códigos de Jurisdicción según la Comisión Arbitral del Convenio Multilateral (SIFERE / CM05)
JURISDICCIONES_SIFERE_MAP = {
    "901": "Ciudad Autónoma de Buenos Aires (CABA)",
    "902": "Buenos Aires (PBA)",
    "903": "Catamarca",
    "904": "Córdoba",
    "905": "Corrientes",
    "906": "Chaco",
    "907": "Chubut",
    "908": "Entre Ríos",
    "909": "Formosa",
    "910": "Jujuy",
    "911": "La Pampa",
    "912": "La Rioja",
    "913": "Mendoza",
    "914": "Misiones",
    "915": "Neuquén",
    "916": "Río Negro",
    "917": "Salta",
    "918": "San Juan",
    "919": "San Luis",
    "920": "Santa Cruz",
    "921": "Santa Fe",
    "922": "Santiago del Estero",
    "923": "Tucumán",
    "924": "Tierra del Fuego",
}

# Mapeo por normalización de nombres de provincias argentinas a código SIFERE
NOMBRE_PROVINCIA_A_CODIGO_SIFERE = {
    "caba": "901",
    "ciudad autonoma de buenos aires": "901",
    "capital federal": "901",
    "buenos aires": "902",
    "pba": "902",
    "catamarca": "903",
    "cordoba": "904",
    "córdoba": "904",
    "corrientes": "905",
    "chaco": "906",
    "chubut": "907",
    "entre rios": "908",
    "entre ríos": "908",
    "formosa": "909",
    "jujuy": "910",
    "la pampa": "911",
    "la rioja": "912",
    "mendoza": "913",
    "misiones": "914",
    "neuquen": "915",
    "neuquén": "915",
    "rio negro": "916",
    "río negro": "916",
    "salta": "917",
    "san juan": "918",
    "san luis": "919",
    "santa cruz": "920",
    "santa fe": "921",
    "santiago del estero": "922",
    "tucuman": "923",
    "tucumán": "923",
    "tierra del fuego": "924",
    "tierra del fuego, antartida e islas del atlantico sur": "924",
}


def resolver_jurisdiccion_documento(doc: DocumentoDeuda) -> str:
    """
    Determina el código de jurisdicción SIFERE (ej: '901', '902') de un comprobante:
    1. Si tiene `jurisdiccion_sifere` explícito en DocumentoDeuda.
    2. Si tiene `provincia_destino` en DocumentoDeuda.
    3. Si el contacto asociado tiene `provincia` cargada.
    4. Fallback: '902' (Buenos Aires - Sede Fabril).
    """
    if doc.jurisdiccion_sifere and doc.jurisdiccion_sifere in JURISDICCIONES_SIFERE_MAP:
        return doc.jurisdiccion_sifere

    prov = (doc.provincia_destino or "").strip().lower()
    if not prov and doc.contacto:
        prov = (getattr(doc.contacto, "provincia", "") or "").strip().lower()

    if prov in NOMBRE_PROVINCIA_A_CODIGO_SIFERE:
        return NOMBRE_PROVINCIA_A_CODIGO_SIFERE[prov]

    return "902"


class ConvenioMultilateralCoeficientesReport(BaseTabularReport):
    """
    Reporte analítico para el cálculo de Coeficientes Unificados de Convenio Multilateral (CM05).
    Conforme al Régimen General (Art. 2° del Convenio Multilateral):
    - 50% en proporción a los Ingresos Brutos devengados por jurisdicción.
    - 50% en proporción a los Gastos Computables devengados por jurisdicción.

    Genera una matriz agregada por las 24 jurisdicciones de la República Argentina,
    calculando los coeficientes de ingresos, coeficientes de gastos y el coeficiente unificado final.
    """

    extension = "xlsx"

    def __init__(
        self,
        periodo_anio: Optional[int] = None,
        fecha_desde: Optional[date] = None,
        fecha_hasta: Optional[date] = None,
        alicuota_default_cm03: Decimal = Decimal("3.00"),
        alicuotas_por_jurisdiccion: Optional[dict] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        if periodo_anio:
            self.fecha_desde = date(periodo_anio, 1, 1)
            self.fecha_hasta = date(periodo_anio, 12, 31)
            self.periodo_anio = periodo_anio
        else:
            self.fecha_desde = fecha_desde
            self.fecha_hasta = fecha_hasta
            self.periodo_anio = fecha_desde.year if fecha_desde else date.today().year

        self.alicuota_default_cm03 = alicuota_default_cm03
        self.alicuotas_por_jurisdiccion = alicuotas_por_jurisdiccion or {}

    @property
    def nombre_archivo(self) -> str:
        return f"Convenio_Multilateral_CM05_{self.periodo_anio}"

    def get_queryset_ingresos(self):
        """Devuelve comprobantes de venta (Facturas, ND y NC a Clientes)."""
        qs = DocumentoDeuda.objects.filter(
            tipo__in=["factura_cliente", "nota_debito_cliente", "nota_credito_cliente"],
            estado__in=["publicado", "pagado", "pagado_parcial"]
        ).select_related("contacto", "tipo_comprobante_afip")

        if self.fecha_desde:
            qs = qs.filter(fecha_emision__gte=self.fecha_desde)
        if self.fecha_hasta:
            qs = qs.filter(fecha_emision__lte=self.fecha_hasta)

        return qs

    def get_queryset_gastos(self):
        """
        Devuelve comprobantes de compras y gastos computables (Facturas, ND y NC de Proveedores, Liquidaciones Fasón).
        Filtra estrictamente los gastos computables conforme al Art. 3° del Convenio Multilateral
        (excluyendo adquisiciones de bienes de uso, intereses financieros y cargas tributarias).
        """
        qs = DocumentoDeuda.objects.filter(
            tipo__in=["factura_proveedor", "nota_debito_proveedor", "nota_credito_proveedor", "liquidacion_fason"],
            estado__in=["publicado", "pagado", "pagado_parcial"],
            gasto_computable_convenio=True,
        ).select_related("contacto", "tipo_comprobante_afip")

        if self.fecha_desde:
            qs = qs.filter(fecha_emision__gte=self.fecha_desde)
        if self.fecha_hasta:
            qs = qs.filter(fecha_emision__lte=self.fecha_hasta)

        return qs

    def get_headers(self) -> List[str]:
        return [
            "Cód. SIFERE",
            "Jurisdicción / Provincia",
            "Ingresos Devengados ($)",
            "Coeficiente Ingresos (%)",
            "Gastos Computables ($)",
            "Coeficiente Gastos (%)",
            "Coeficiente Unificado CM05 (%)",
            "Base Imponible Atribuida ($)",
            "Alícuota IIBB Actividad (%)",
            "Impuesto Determinado Estimado CM03 ($)",
        ]

    def get_rows(self) -> List[List[Any]]:
        from apps.contabilidad.models import Impuesto

        # Cargar alícuotas de IIBB provinciales configuradas en Impuesto
        alicuotas_db = {}
        for imp in Impuesto.objects.filter(tipo__in=["percepcion_iibb", "retencion_iibb", "otro"], activo=True):
            if imp.jurisdiccion_sifere:
                alicuotas_db[imp.jurisdiccion_sifere] = imp.alicuota

        # Inicializar acumuladores para las 24 jurisdicciones
        ingresos_por_jurisdiccion = {cod: Decimal("0.00") for cod in JURISDICCIONES_SIFERE_MAP}
        gastos_por_jurisdiccion = {cod: Decimal("0.00") for cod in JURISDICCIONES_SIFERE_MAP}

        # 1. Acumular Ingresos
        for doc in self.get_queryset_ingresos():
            cod = resolver_jurisdiccion_documento(doc)
            signo = -1 if doc.tipo == "nota_credito_cliente" else 1
            # Para CM05 se toma el Monto Neto Gravado / Total Ingresos sin IVA
            monto_ingreso = doc.monto_neto * signo
            ingresos_por_jurisdiccion[cod] += monto_ingreso

        # 2. Acumular Gastos
        for doc in self.get_queryset_gastos():
            cod = resolver_jurisdiccion_documento(doc)
            signo = -1 if doc.tipo == "nota_credito_proveedor" else 1
            monto_gasto = doc.monto_neto * signo
            gastos_por_jurisdiccion[cod] += monto_gasto

        # Totales globales
        total_ingresos = sum(ingresos_por_jurisdiccion.values())
        total_gastos = sum(gastos_por_jurisdiccion.values())

        rows = []
        total_base_atribuida = Decimal("0.00")
        total_impuesto_estimado = Decimal("0.00")

        for cod, nombre_prov in sorted(JURISDICCIONES_SIFERE_MAP.items()):
            ing = ingresos_por_jurisdiccion[cod]
            gas = gastos_por_jurisdiccion[cod]

            # Coeficientes en base 100 (4 decimales según formato oficial SIFERE)
            coef_ing = round((ing / total_ingresos) * Decimal("100.0"), 4) if total_ingresos > Decimal("0.00") else Decimal("0.0000")
            coef_gas = round((gas / total_gastos) * Decimal("100.0"), 4) if total_gastos > Decimal("0.00") else Decimal("0.0000")

            # Coeficiente Unificado = (Coef. Ingresos + Coef. Gastos) / 2
            coef_unif = round((coef_ing + coef_gas) / Decimal("2.0"), 4)

            # Determinación de Base Imponible Atribuida mensual/anual y liquidación CM03
            base_atribuida = round((total_ingresos * coef_unif) / Decimal("100.0"), 2)
            alicuota_aplicable = (
                self.alicuotas_por_jurisdiccion.get(cod)
                or alicuotas_db.get(cod)
                or self.alicuota_default_cm03
            )
            impuesto_estimado = round((base_atribuida * Decimal(str(alicuota_aplicable))) / Decimal("100.0"), 2)

            total_base_atribuida += base_atribuida
            total_impuesto_estimado += impuesto_estimado

            rows.append([
                cod,
                nombre_prov,
                float(ing),
                float(coef_ing),
                float(gas),
                float(coef_gas),
                float(coef_unif),
                float(base_atribuida),
                float(alicuota_aplicable),
                float(impuesto_estimado),
            ])

        # Fila de Totales
        rows.append([
            "TOTAL",
            "TOTAL PAÍS (Consolidado)",
            float(total_ingresos),
            100.0 if total_ingresos > 0 else 0.0,
            float(total_gastos),
            100.0 if total_gastos > 0 else 0.0,
            100.0 if (total_ingresos > 0 and total_gastos > 0) else 0.0,
            float(total_base_atribuida),
            float(self.alicuota_default_cm03),
            float(total_impuesto_estimado),
        ])

        return rows
