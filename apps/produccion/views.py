from django.shortcuts import get_object_or_404, redirect
from django.views.generic import ListView, DetailView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from .models import OrdenProduccion
from .services import ProduccionService

class OPListView(LoginRequiredMixin, ListView):
    model = OrdenProduccion
    template_name = "produccion/op_list.html"
    context_object_name = "ops"
    paginate_by = 20

    def get_queryset(self):
        # TODO: Filtrar por rol (Ej. Si es tallerista, ver solo las suyas)
        # Por ahora mostramos todas ordenadas por las más recientes
        return OrdenProduccion.objects.all().order_by('-fecha', '-id')


class OPDetailView(LoginRequiredMixin, DetailView):
    model = OrdenProduccion
    template_name = "produccion/op_detail.html"
    context_object_name = "op"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Agregamos data extra necesaria para la vista
        context['insumos'] = self.object.insumos_requeridos.all()
        context['variaciones'] = self.object.variaciones.all()
        context['etapas'] = self.object.tracking_etapas.all()
        return context


# =====================================================================
# ACTION VIEWS (Llaman a la Capa de Servicios)
# Solo aceptan método POST por seguridad (previene CSRF via links GET)
# =====================================================================

class OPConfirmarActionView(LoginRequiredMixin, View):
    def post(self, request, pk):
        op = get_object_or_404(OrdenProduccion, pk=pk)
        try:
            ProduccionService.confirmar_op(op)
            messages.success(request, f"e-OP {op.numero} confirmada exitosamente. Hash sellado y stock reservado.")
        except Exception as e:
            messages.error(request, f"Error al confirmar la e-OP: {str(e)}")
        
        return redirect('produccion:op_detail', pk=op.pk)


class OPFinalizarActionView(LoginRequiredMixin, View):
    def post(self, request, pk):
        op = get_object_or_404(OrdenProduccion, pk=pk)
        try:
            ProduccionService.finalizar_op(op)
            messages.success(request, f"e-OP {op.numero} finalizada. Producto terminado ingresado al stock.")
        except Exception as e:
            messages.error(request, f"Error al finalizar la e-OP: {str(e)}")
        
        return redirect('produccion:op_detail', pk=op.pk)


class OPCancelarActionView(LoginRequiredMixin, View):
    def post(self, request, pk):
        op = get_object_or_404(OrdenProduccion, pk=pk)
        try:
            ProduccionService.cancelar_op(op)
            messages.warning(request, f"e-OP {op.numero} cancelada. Reservas liberadas.")
        except Exception as e:
            messages.error(request, f"Error al cancelar la e-OP: {str(e)}")
        
        return redirect('produccion:op_detail', pk=op.pk)
