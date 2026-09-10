from django.shortcuts import get_object_or_404, redirect
from django.views.generic import ListView, DetailView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from .models import DocumentoDeuda
from .servicios_afip import FacturadorAFIP

class DocumentoDeudaListView(LoginRequiredMixin, ListView):
    model = DocumentoDeuda
    template_name = "contabilidad/factura_list.html"
    context_object_name = "documentos"
    paginate_by = 30

    def get_queryset(self):
        return DocumentoDeuda.objects.all().order_by('-fecha_emision', '-id')


class DocumentoDeudaDetailView(LoginRequiredMixin, DetailView):
    model = DocumentoDeuda
    template_name = "contabilidad/factura_detail.html"
    context_object_name = "documento"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['lineas'] = self.object.lineas.all()
        return context


# =====================================================================
# ACTION VIEWS
# =====================================================================

class EmitirAFIPActionView(LoginRequiredMixin, View):
    def post(self, request, pk):
        doc = get_object_or_404(DocumentoDeuda, pk=pk)
        
        try:
            # El entorno (homologacion/produccion) se lee automáticamente de ConfiguracionEmpresa
            facturador = FacturadorAFIP()
            facturador.emitir_comprobante(doc)
            messages.success(request, f"Comprobante {doc.numero} emitido en AFIP con CAE {doc.afip_cae}.")
        except Exception as e:
            messages.error(request, f"Error al emitir en AFIP: {str(e)}")
        
        return redirect('contabilidad:factura_detail', pk=doc.pk)
