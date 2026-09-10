from django.shortcuts import get_object_or_404, redirect
from django.views.generic import ListView, DetailView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from .models import OrdenCompra
from .services import ComprasService

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
