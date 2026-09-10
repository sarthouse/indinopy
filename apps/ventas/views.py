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


class ConfirmarOVActionView(LoginRequiredMixin, View):
    def post(self, request, pk):
        ov = get_object_or_404(OrdenVenta, pk=pk)
        
        try:
            # TODO: Crear VentasService y generar remito de salida
            ov.estado = "confirmado"
            ov.save(update_fields=["estado"])
            messages.success(request, f"Orden de Venta {ov.numero} confirmada.")
        except Exception as e:
            messages.error(request, f"Error al confirmar la OV: {str(e)}")
        
        return redirect('ventas:ov_detail', pk=ov.pk)
