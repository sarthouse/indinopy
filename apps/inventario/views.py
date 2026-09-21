from django.shortcuts import get_object_or_404, redirect
from django.views.generic import ListView, DetailView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from .models import StockQuant, MovimientoStock, LineaMovimientoStock
from .services import StockService
from .reports.remito_report import RemitoPDFReport

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


from datetime import datetime
from .reports.inventario_stock_report import InventarioStockExcelReport
from .reports.movimientos_stock_report import MovimientosStockExcelReport


class RemitoPDFDownloadView(LoginRequiredMixin, View):
    """Descarga o previsualización inline del Remito (Entrega, Traslado a Producción o Traslado Interno)."""
    def get(self, request, pk):
        movimiento = get_object_or_404(MovimientoStock, pk=pk)
        report = RemitoPDFReport(movimiento)
        inline = request.GET.get("inline", "true").lower() == "true"
        return report.to_http_response(inline=inline)


class InventarioStockExportView(LoginRequiredMixin, View):
    """Exportación en Excel o CSV del inventario físico y stock valuado."""
    def get(self, request):
        formato = request.GET.get("formato", "xlsx")
        ubicacion_id = request.GET.get("ubicacion_id")
        tipo_ubicacion = request.GET.get("tipo_ubicacion")
        categoria_id = request.GET.get("categoria_id")
        tipo_producto = request.GET.get("tipo_producto")
        solo_con_stock = request.GET.get("solo_con_stock", "true").lower() == "true"

        report = InventarioStockExcelReport(
            ubicacion_id=int(ubicacion_id) if ubicacion_id and ubicacion_id.isdigit() else None,
            tipo_ubicacion=tipo_ubicacion,
            categoria_id=int(categoria_id) if categoria_id and categoria_id.isdigit() else None,
            tipo_producto=tipo_producto,
            solo_con_stock=solo_con_stock,
        )
        return report.to_http_response(formato=formato)


class MovimientosStockExportView(LoginRequiredMixin, View):
    """Exportación en Excel o CSV de la trazabilidad y movimientos de stock (Kardex general)."""
    def get(self, request):
        formato = request.GET.get("formato", "xlsx")
        fecha_desde_raw = request.GET.get("desde")
        fecha_hasta_raw = request.GET.get("hasta")
        tipo_movimiento = request.GET.get("tipo")
        producto_id = request.GET.get("producto_id")
        ubicacion_id = request.GET.get("ubicacion_id")
        estado = request.GET.get("estado")

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

        report = MovimientosStockExcelReport(
            fecha_desde=f_desde,
            fecha_hasta=f_hasta,
            tipo_movimiento=tipo_movimiento,
            producto_id=int(producto_id) if producto_id and producto_id.isdigit() else None,
            ubicacion_id=int(ubicacion_id) if ubicacion_id and ubicacion_id.isdigit() else None,
            estado=estado,
        )
        return report.to_http_response(formato=formato)


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
