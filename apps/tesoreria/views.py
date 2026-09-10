from django.shortcuts import get_object_or_404, redirect
from django.views.generic import ListView, DetailView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from .models import ContratoEscrow, HitoEscrow
from .services import EscrowService

class EscrowListView(LoginRequiredMixin, ListView):
    model = ContratoEscrow
    template_name = "tesoreria/escrow_list.html"
    context_object_name = "escrows"
    paginate_by = 20

    def get_queryset(self):
        return ContratoEscrow.objects.all().order_by('-creado_en')


class EscrowDetailView(LoginRequiredMixin, DetailView):
    model = ContratoEscrow
    template_name = "tesoreria/escrow_detail.html"
    context_object_name = "escrow"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['hitos'] = self.object.hitos.all().order_by('id')
        return context


# =====================================================================
# ACTION VIEWS
# =====================================================================

class LiberarHitoActionView(LoginRequiredMixin, View):
    def post(self, request, pk):
        hito = get_object_or_404(HitoEscrow, pk=pk)
        escrow_pk = hito.contrato.pk
        
        # En una app real, acá se leería la firma (ej. de un campo oculto del form o un header)
        # Por ahora lo pasamos hardcodeado o como venga en el request POST
        # firma_ptf = request.POST.get('firma_ptf')
        
        try:
            # Como aún no implementamos validación crypto completa, dejamos que el service confíe
            # o podemos simplemente simularlo para testing.
            EscrowService.liberar_hito(hito.pk, firma_ptf=True) 
            messages.success(request, f"Hito '{hito.nombre}' liberado. Se generó la orden de pago.")
        except Exception as e:
            messages.error(request, f"Error al liberar hito: {str(e)}")
        
        return redirect('tesoreria:escrow_detail', pk=escrow_pk)


class FondearEscrowActionView(LoginRequiredMixin, View):
    def post(self, request, pk):
        escrow = get_object_or_404(ContratoEscrow, pk=pk)
        comprobante_id = request.POST.get('comprobante_id')
        
        try:
            EscrowService.fondear_escrow(escrow.pk, comprobante_id)
            messages.success(request, f"Contrato Escrow fondeado exitosamente.")
        except Exception as e:
            messages.error(request, f"Error al fondear el Escrow: {str(e)}")
        
        return redirect('tesoreria:escrow_detail', pk=escrow.pk)
