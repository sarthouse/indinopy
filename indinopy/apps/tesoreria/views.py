from django.views.generic import ListView, DetailView
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
