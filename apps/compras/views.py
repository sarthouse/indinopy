from django.shortcuts import get_object_or_404, redirect
from django.views.generic import ListView, DetailView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from .models import OrdenCompra
from .services import ComprasService
from .reports import (
    OrdenCompraPDFReport,
    SolicitudCotizacionPDFReport,
    RecepcionesPendientesExcelReport,
)


class OrdenCompraListView(LoginRequiredMixin, ListView):
    model = OrdenCompra
    template_name = "compras/oc_list.html"
    context_object_name = "ordenes"
    paginate_by = 20

    def get_queryset(self):
        return OrdenCompra.objects.all().order_by('-fecha', '-id')


class OrdenCompraDetailView(LoginRequiredMixin, DetailView):
    model = OrdenCompra
    template_name = "compras/oc_detail.html"
    context_object_name = "oc"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['lineas'] = self.object.lineas.all()
        return context


class OrdenCompraPDFDownloadView(LoginRequiredMixin, View):
    """Descarga o previsualización inline de la Orden de Compra oficial en PDF."""
    def get(self, request, pk):
        oc = get_object_or_404(OrdenCompra, pk=pk)
        report = OrdenCompraPDFReport(oc)
        inline = request.GET.get("inline", "true").lower() == "true"
        return report.to_http_response(inline=inline)


class SolicitudCotizacionPDFDownloadView(LoginRequiredMixin, View):
    """Descarga o previsualización inline de la Solicitud de Cotización (RFQ) en PDF."""
    def get(self, request, pk):
        oc = get_object_or_404(OrdenCompra, pk=pk)
        report = SolicitudCotizacionPDFReport(oc)
        inline = request.GET.get("inline", "true").lower() == "true"
        return report.to_http_response(inline=inline)


class RecepcionesPendientesExportView(LoginRequiredMixin, View):
    """Exportación en Excel o CSV de los insumos y órdenes pendientes de recibir (Backorders)."""
    def get(self, request):
        formato = request.GET.get("formato", "xlsx")
        proveedor_id = request.GET.get("proveedor_id")
        solo_vencidas = request.GET.get("solo_vencidas", "false").lower() == "true"

        report = RecepcionesPendientesExcelReport(
            proveedor_id=int(proveedor_id) if proveedor_id and proveedor_id.isdigit() else None,
            solo_vencidas=solo_vencidas,
        )

        if formato == "csv":
            return report.to_csv_response()
        return report.to_excel_response()


# =====================================================================
# ACTION VIEWS
# =====================================================================

class ConfirmarOCActionView(LoginRequiredMixin, View):
    def post(self, request, pk):
        oc = get_object_or_404(OrdenCompra, pk=pk)
        try:
            ComprasService.confirmar_oc(oc)
            messages.success(request, f"Orden de Compra {oc.numero} confirmada. Recepciones de stock generadas.")
        except Exception as e:
            messages.error(request, f"Error al confirmar la OC: {str(e)}")
        
        return redirect('compras:oc_detail', pk=oc.pk)


class CancelarOCActionView(LoginRequiredMixin, View):
    def post(self, request, pk):
        oc = get_object_or_404(OrdenCompra, pk=pk)
        try:
            ComprasService.cancelar_oc(oc)
            messages.warning(request, f"Orden de Compra {oc.numero} cancelada.")
        except Exception as e:
            messages.error(request, f"Error al cancelar la OC: {str(e)}")
        
        return redirect('compras:oc_detail', pk=oc.pk)


class FacturarOCActionView(LoginRequiredMixin, View):
    """
    Genera un DocumentoDeuda (Factura de Compra) en borrador a partir de la OC.
    Permite elegir facturar lo efectivamente recibido o la totalidad pedida.
    """
    def post(self, request, pk):
        oc = get_object_or_404(OrdenCompra, pk=pk)
        numero_factura = request.POST.get("numero_factura")
        basado_en = request.POST.get("basado_en", "recibido")

        if not numero_factura:
            messages.error(request, "Debe indicar el número de factura del proveedor.")
            return redirect('compras:oc_detail', pk=oc.pk)

        try:
            factura = ComprasService.crear_factura_proveedor(
                oc=oc,
                numero_factura=numero_factura,
                basado_en=basado_en,
            )
            messages.success(
                request,
                f"Factura de Proveedor {factura.numero} creada exitosamente en Contabilidad (Monto: {factura.monto_total})."
            )
        except Exception as e:
            messages.error(request, f"Error al facturar la OC: {str(e)}")

        return redirect('compras:oc_detail', pk=oc.pk)
