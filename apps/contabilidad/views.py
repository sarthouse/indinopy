from datetime import datetime
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import ListView, DetailView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from .models import DocumentoDeuda
from .servicios_afip import FacturadorAFIP
from .reports.comprobante_report import ComprobanteFiscalPDFReport
from .reports.libro_iva_report import LibroIVAVentasExcelReport, LibroIVAComprasExcelReport
from .reports.convenio_multilateral_report import ConvenioMultilateralCoeficientesReport

class DocumentoDeudaListView(LoginRequiredMixin, ListView):
    model = DocumentoDeuda
    template_name = "contabilidad/factura_list.html"
    context_object_name = "documentos"
    paginate_by = 30

    def get_queryset(self):
        return DocumentoDeuda.objects.all().order_by('-fecha_emision', '-id')


class DocumentoDeudaDetailView(LoginRequiredMixin, DetailView):
    model = DocumentoDeuda
    template_name = "contabilidad/factura_detail.html"
    context_object_name = "documento"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['lineas'] = self.object.lineas.all()
        return context


class ComprobantePDFDownloadView(LoginRequiredMixin, View):
    """Descarga o visualización inline del PDF oficial del comprobante."""
    def get(self, request, pk):
        doc = get_object_or_404(DocumentoDeuda, pk=pk)
        report = ComprobanteFiscalPDFReport(doc)
        inline = request.GET.get("inline", "true").lower() == "true"
        return report.to_http_response(inline=inline)


class LibroIVAVentasExportView(LoginRequiredMixin, View):
    """Exportación en Excel del Libro IVA Ventas según filtros de fecha y diario."""
    def get(self, request):
        fecha_desde = request.GET.get("desde")
        fecha_hasta = request.GET.get("hasta")
        diario_id = request.GET.get("diario")
        formato = request.GET.get("formato", "xlsx")

        report = LibroIVAVentasExcelReport(
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            diario_id=diario_id,
        )
        return report.to_http_response(formato=formato)


class LibroIVAComprasExportView(LoginRequiredMixin, View):
    """Exportación en Excel del Libro IVA Compras según filtros de fecha y diario."""
    def get(self, request):
        fecha_desde = request.GET.get("desde")
        fecha_hasta = request.GET.get("hasta")
        diario_id = request.GET.get("diario")
        formato = request.GET.get("formato", "xlsx")

        report = LibroIVAComprasExcelReport(
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            diario_id=diario_id,
        )
        return report.to_http_response(formato=formato)


class ConvenioMultilateralExportView(LoginRequiredMixin, View):
    """
    Exportación en Excel de la matriz provincial de ingresos y gastos para
    la determinación de coeficientes unificados de Convenio Multilateral (CM05).
    """
    def get(self, request):
        periodo_anio = request.GET.get("anio")
        fecha_desde_raw = request.GET.get("desde")
        fecha_hasta_raw = request.GET.get("hasta")
        formato = request.GET.get("formato", "xlsx")

        f_desde = None
        if fecha_desde_raw:
            try:
                f_desde = datetime.strptime(fecha_desde_raw, "%Y-%m-%d").date()
            except ValueError:
                pass

        f_hasta = None
        if fecha_hasta_raw:
            try:
                f_hasta = datetime.strptime(fecha_hasta_raw, "%Y-%m-%d").date()
            except ValueError:
                pass

        report = ConvenioMultilateralCoeficientesReport(
            periodo_anio=int(periodo_anio) if periodo_anio and periodo_anio.isdigit() else None,
            fecha_desde=f_desde,
            fecha_hasta=f_hasta,
        )
        return report.to_http_response(formato=formato)


# =====================================================================
# ACTION VIEWS
# =====================================================================

class EmitirAFIPActionView(LoginRequiredMixin, View):
    def post(self, request, pk):
        doc = get_object_or_404(DocumentoDeuda, pk=pk)
        
        try:
            if not doc.diario.es_facturacion_electronica:
                messages.info(request, f"El diario {doc.diario.codigo} no opera con AFIP. El comprobante se considera confirmado de forma interna.")
            else:
                facturador = FacturadorAFIP()
                facturador.emitir_comprobante(doc)
                messages.success(request, f"Comprobante {doc.numero} emitido en AFIP con CAE {doc.afip_cae}.")
        except Exception as e:
            messages.error(request, f"Error al emitir en AFIP: {str(e)}")
        
        return redirect('contabilidad:factura_detail', pk=doc.pk)
