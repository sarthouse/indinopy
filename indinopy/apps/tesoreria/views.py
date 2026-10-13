from django.views.generic import ListView, DetailView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import ComprobanteTesoreria

class ComprobanteTesoreriaListView(LoginRequiredMixin, ListView):
    model = ComprobanteTesoreria
    template_name = "tesoreria/comprobante_list.html"
    context_object_name = "comprobantes"
    paginate_by = 30

    def get_queryset(self):
        # Ordenamos por fecha de emisión más reciente
        return ComprobanteTesoreria.objects.all().order_by('-fecha_emision', '-id')


class ComprobanteTesoreriaDetailView(LoginRequiredMixin, DetailView):
    model = ComprobanteTesoreria
    template_name = "tesoreria/comprobante_detail.html"
    context_object_name = "comprobante"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Pasamos las aplicaciones (pagos de facturas) vinculadas a este comprobante
        # Esto asume que tienes un related_name="aplicaciones_emitidas" en AplicacionPago
        context['aplicaciones'] = self.object.aplicaciones_emitidas.all()
        # Pasamos también los movimientos de caja/banco si hicieran falta
        context['movimientos'] = self.object.movimientos_caja.all()
        return context


class ConfirmarComprobanteActionView(LoginRequiredMixin, View):
    """
    Confirma un comprobante de tesorería (Orden de Pago o Recibo de Cobro)
    impactando las cajas/bancos y procesando repagos de fideicomiso si aplica.
    """
    def post(self, request, pk):
        from django.shortcuts import get_object_or_404, redirect
        from django.contrib import messages
        from .services import TesoreriaService

        comprobante = get_object_or_404(ComprobanteTesoreria, pk=pk)
        
        try:
            comprobante.estado = "confirmado"
            comprobante.save(update_fields=["estado"])
            TesoreriaService.procesar_repago_marca(comprobante.id)

            messages.success(
                request,
                f"Comprobante {comprobante.numero} ({comprobante.get_tipo_display()}) confirmado exitosamente. "
                f"Monto total: ${comprobante.monto_total:.2f}. Fondos imputados en tesorería."
            )
        except Exception as exc:
            messages.error(
                request,
                f"Error al confirmar el comprobante de tesorería: {str(exc)}"
            )

        return redirect('tesoreria:comprobante_detail', pk=comprobante.pk)
