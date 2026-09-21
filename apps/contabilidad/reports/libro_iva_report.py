from datetime import date
from decimal import Decimal
from typing import Any, List, Optional
from apps.base.reports.base import BaseTabularReport
from apps.contabilidad.models import DocumentoDeuda


class LibroIVAVentasExcelReport(BaseTabularReport):
    """
    Reporte tabular de Libro IVA Ventas Digital para exportación a Excel / CSV.
    Agrupa comprobantes emitidos en un período fiscal con discriminación de bases imponibles,
    alícuotas de IVA y percepciones provinciales/nacionales (AFIP / ARCA).
    """

    extension = "xlsx"

    def __init__(
        self,
        fecha_desde: Optional[date] = None,
        fecha_hasta: Optional[date] = None,
        diario_id: Optional[int] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.fecha_desde = fecha_desde
        self.fecha_hasta = fecha_hasta
        self.diario_id = diario_id

    @property
    def nombre_archivo(self) -> str:
        periodo = ""
        if self.fecha_desde and self.fecha_hasta:
            periodo = f"_{self.fecha_desde.strftime('%Y%m')}"
        return f"Libro_IVA_Ventas{periodo}"

    def get_queryset(self):
        qs = DocumentoDeuda.objects.filter(
            tipo__in=["factura_cliente", "nota_debito_cliente", "nota_credito_cliente"],
            estado__in=["publicado", "pagado", "pagado_parcial"]
        ).select_related("contacto", "tipo_comprobante_afip", "diario").prefetch_related("lineas__impuesto", "tributos")

        if self.fecha_desde:
            qs = qs.filter(fecha_emision__gte=self.fecha_desde)
        if self.fecha_hasta:
            qs = qs.filter(fecha_emision__lte=self.fecha_hasta)
        if self.diario_id:
            qs = qs.filter(diario_id=self.diario_id)

        return qs.order_by("fecha_emision", "numero")

    def get_headers(self) -> List[str]:
        return [
            "Fecha",
            "Tipo Cbte",
            "Pto Vta",
            "Número",
            "Doc Tipo",
            "Doc Nro (CUIT/DNI)",
            "Cliente / Razón Social",
            "Condición IVA",
            "Neto Gravado",
            "No Gravado / Exento",
            "IVA 21%",
            "IVA 10.5%",
            "IVA 27%",
            "Total IVA",
            "Percepciones IIBB",
            "Otras Percepciones / Tributos",
            "Total Facturado",
            "CAE",
        ]

    def get_rows(self) -> List[List[Any]]:
        rows = []
        for doc in self.get_queryset():
            # Signo multiplicador según el comprobante (Notas de crédito van negativas en el reporte fiscal)
            signo = -1 if doc.tipo == "nota_credito_cliente" else 1

            # Desglose de IVA por alícuota
            iva_21 = Decimal("0.00")
            iva_105 = Decimal("0.00")
            iva_27 = Decimal("0.00")

            for linea in doc.lineas.all():
                if linea.impuesto and linea.impuesto.tipo == "iva":
                    alicuota = linea.impuesto.alicuota
                    monto_iva = linea.subtotal * (alicuota / Decimal("100.0"))
                    if alicuota == Decimal("21.00"):
                        iva_21 += monto_iva
                    elif alicuota == Decimal("10.50"):
                        iva_105 += monto_iva
                    elif alicuota == Decimal("27.00"):
                        iva_27 += monto_iva

            total_iva = doc.monto_impuestos

            # Desglose de percepciones de venta
            percep_iibb = Decimal("0.00")
            otras_percep = Decimal("0.00")
            for trib in doc.tributos.all():
                if trib.afip_tributo_id == 2:  # IIBB
                    percep_iibb += trib.importe
                else:
                    otras_percep += trib.importe

            # Fallback si monto_tributos fue cargado directo
            if doc.monto_tributos > 0 and percep_iibb == Decimal("0.00") and otras_percep == Decimal("0.00"):
                otras_percep = doc.monto_tributos

            pto_vta = ""
            nro_cbte = doc.numero
            if "-" in doc.numero:
                partes = doc.numero.split("-")
                if len(partes) == 2:
                    pto_vta = partes[0]
                    nro_cbte = partes[1]

            rows.append([
                doc.fecha_emision.strftime("%d/%m/%Y"),
                doc.tipo_comprobante_afip.codigo if doc.tipo_comprobante_afip else "001",
                pto_vta,
                nro_cbte,
                "80" if len(doc.contacto.cuil or "") == 11 else "96",
                doc.contacto.cuil or "",
                doc.contacto.nombre,
                doc.contacto.get_condicion_iva_display() if hasattr(doc.contacto, "get_condicion_iva_display") else doc.contacto.condicion_iva,
                float(doc.monto_neto * signo),
                0.0,
                float(iva_21 * signo),
                float(iva_105 * signo),
                float(iva_27 * signo),
                float(total_iva * signo),
                float(percep_iibb * signo),
                float(otras_percep * signo),
                float(doc.monto_total * signo),
                doc.afip_cae or "",
            ])

        return rows


class LibroIVAComprasExcelReport(BaseTabularReport):
    """
    Reporte tabular de Libro IVA Compras Digital para exportación a Excel / CSV.
    Agrupa facturas de proveedores, liquidaciones de fasón y notas de crédito de compra,
    discriminando crédito fiscal IVA y percepciones provinciales (IIBB) y nacionales (IVA).
    """

    extension = "xlsx"

    def __init__(
        self,
        fecha_desde: Optional[date] = None,
        fecha_hasta: Optional[date] = None,
        diario_id: Optional[int] = None,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.fecha_desde = fecha_desde
        self.fecha_hasta = fecha_hasta
        self.diario_id = diario_id

    @property
    def nombre_archivo(self) -> str:
        periodo = ""
        if self.fecha_desde and self.fecha_hasta:
            periodo = f"_{self.fecha_desde.strftime('%Y%m')}"
        return f"Libro_IVA_Compras{periodo}"

    def get_queryset(self):
        qs = DocumentoDeuda.objects.filter(
            tipo__in=["factura_proveedor", "nota_debito_proveedor", "nota_credito_proveedor", "liquidacion_fason"],
            estado__in=["publicado", "pagado", "pagado_parcial"]
        ).select_related("contacto", "tipo_comprobante_afip", "diario").prefetch_related("lineas__impuesto", "tributos")

        if self.fecha_desde:
            qs = qs.filter(fecha_emision__gte=self.fecha_desde)
        if self.fecha_hasta:
            qs = qs.filter(fecha_emision__lte=self.fecha_hasta)
        if self.diario_id:
            qs = qs.filter(diario_id=self.diario_id)

        return qs.order_by("fecha_emision", "numero")

    def get_headers(self) -> List[str]:
        return [
            "Fecha",
            "Tipo Cbte",
            "Pto Vta",
            "Número",
            "Doc Tipo",
            "CUIT Proveedor",
            "Proveedor / Razón Social",
            "Condición IVA",
            "Neto Gravado",
            "No Gravado / Exento",
            "IVA 21%",
            "IVA 10.5%",
            "IVA 27%",
            "Total Crédito IVA",
            "Percepción IVA",
            "Percepción IIBB",
            "Otras Percepciones / Impuestos",
            "Total Facturado",
            "CAE",
        ]

    def get_rows(self) -> List[List[Any]]:
        rows = []
        for doc in self.get_queryset():
            signo = -1 if doc.tipo == "nota_credito_proveedor" else 1

            iva_21 = Decimal("0.00")
            iva_105 = Decimal("0.00")
            iva_27 = Decimal("0.00")

            for linea in doc.lineas.all():
                if linea.impuesto and linea.impuesto.tipo == "iva":
                    alicuota = linea.impuesto.alicuota
                    monto_iva = linea.subtotal * (alicuota / Decimal("100.0"))
                    if alicuota == Decimal("21.00"):
                        iva_21 += monto_iva
                    elif alicuota == Decimal("10.50"):
                        iva_105 += monto_iva
                    elif alicuota == Decimal("27.00"):
                        iva_27 += monto_iva

            total_iva = doc.monto_impuestos

            percep_iva = Decimal("0.00")
            percep_iibb = Decimal("0.00")
            otras_percep = Decimal("0.00")

            for trib in doc.tributos.all():
                if trib.afip_tributo_id == 1:  # Percepción IVA / Impuestos Nacionales
                    percep_iva += trib.importe
                elif trib.afip_tributo_id == 2:  # Percepción IIBB
                    percep_iibb += trib.importe
                else:
                    otras_percep += trib.importe

            if doc.monto_tributos > 0 and percep_iva == Decimal("0.00") and percep_iibb == Decimal("0.00") and otras_percep == Decimal("0.00"):
                otras_percep = doc.monto_tributos

            pto_vta = ""
            nro_cbte = doc.numero
            if "-" in doc.numero:
                partes = doc.numero.split("-")
                if len(partes) == 2:
                    pto_vta = partes[0]
                    nro_cbte = partes[1]

            rows.append([
                doc.fecha_emision.strftime("%d/%m/%Y"),
                doc.tipo_comprobante_afip.codigo if doc.tipo_comprobante_afip else "001",
                pto_vta,
                nro_cbte,
                "80" if len(doc.contacto.cuil or "") == 11 else "96",
                doc.contacto.cuil or "",
                doc.contacto.nombre,
                doc.contacto.get_condicion_iva_display() if hasattr(doc.contacto, "get_condicion_iva_display") else doc.contacto.condicion_iva,
                float(doc.monto_neto * signo),
                0.0,
                float(iva_21 * signo),
                float(iva_105 * signo),
                float(iva_27 * signo),
                float(total_iva * signo),
                float(percep_iva * signo),
                float(percep_iibb * signo),
                float(otras_percep * signo),
                float(doc.monto_total * signo),
                doc.afip_cae or "",
            ])

        return rows

