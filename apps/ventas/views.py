from django.shortcuts import get_object_or_404, redirect
from django.views.generic import ListView, DetailView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from .models import OrdenVenta

class OrdenVentaListView(LoginRequiredMixin, ListView):
    model = OrdenVenta
    template_name = "ventas/ov_list.html"
    context_object_name = "ordenes"
    paginate_by = 20

    def get_queryset(self):
        return OrdenVenta.objects.all().order_by('-fecha', '-id')


class OrdenVentaDetailView(LoginRequiredMixin, DetailView):
    model = OrdenVenta
    template_name = "ventas/ov_detail.html"
    context_object_name = "ov"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['lineas'] = self.object.lineas.all()
        return context


class PresupuestoPDFDownloadView(LoginRequiredMixin, View):
    """Descarga o previsualización inline del Presupuesto o Nota de Pedido en PDF."""
    def get(self, request, pk):
        from .reports.presupuesto_report import PresupuestoPDFReport
        ov = get_object_or_404(OrdenVenta, pk=pk)
        report = PresupuestoPDFReport(ov)
        inline = request.GET.get("inline", "true").lower() == "true"
        return report.to_http_response(inline=inline)


class ConfirmarOVActionView(LoginRequiredMixin, View):
    def post(self, request, pk):
        ov = get_object_or_404(OrdenVenta, pk=pk)
        
        try:
            from .services import VentasService
            ov.estado = "confirmado"
            ov.save(update_fields=["estado"])
            VentasService.generar_remito_salida(ov)
            messages.success(request, f"Orden de Venta {ov.numero} confirmada y remito de salida generado.")
        except Exception as e:
            messages.error(request, f"Error al confirmar la OV: {str(e)}")
        
        return redirect('ventas:ov_detail', pk=ov.pk)
