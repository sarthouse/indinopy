from django.shortcuts import get_object_or_404, redirect
from django.views.generic import ListView, DetailView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from .models import StockQuant, MovimientoStock, LineaMovimientoStock
from .services import StockService

class StockQuantListView(LoginRequiredMixin, ListView):
    model = StockQuant
    template_name = "inventario/quant_list.html"
    context_object_name = "quants"
    paginate_by = 30

    def get_queryset(self):
        return StockQuant.objects.filter(cantidad_fisica__gt=0).order_by('ubicacion', 'producto')


class MovimientoStockListView(LoginRequiredMixin, ListView):
    model = MovimientoStock
    template_name = "inventario/movimiento_list.html"
    context_object_name = "movimientos"
    paginate_by = 20

    def get_queryset(self):
        return MovimientoStock.objects.all().order_by('-fecha', '-id')


class MovimientoStockDetailView(LoginRequiredMixin, DetailView):
    model = MovimientoStock
    template_name = "inventario/movimiento_detail.html"
    context_object_name = "movimiento"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['lineas'] = self.object.lineas.all()
        return context


# =====================================================================
# ACTION VIEWS
# =====================================================================

class RealizarLineaActionView(LoginRequiredMixin, View):
    def post(self, request, pk):
        linea = get_object_or_404(LineaMovimientoStock, pk=pk)
        movimiento_pk = linea.movimiento.pk
        
        # Opcionalmente se puede recoger la cantidad realizada desde un input
        # qty = request.POST.get('cantidad_hecha')
        # if qty:
        #     linea.cantidad_hecha = qty
        #     linea.save()
            
        try:
            StockService.realizar_linea(linea)
            messages.success(request, f"Línea de {linea.producto} marcada como realizada.")
        except Exception as e:
            messages.error(request, f"Error al procesar el stock: {str(e)}")
        
        return redirect('inventario:movimiento_detail', pk=movimiento_pk)
