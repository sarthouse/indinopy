import json
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import ListView, DetailView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from .models import ContratoEOP, EOPHitoEscrow
from .services import EOPService

class ContratoEOPListView(LoginRequiredMixin, ListView):
    model = ContratoEOP
    template_name = "eop/contrato_list.html"
    context_object_name = "contratos"
    paginate_by = 20

    def get_queryset(self):
        return ContratoEOP.objects.all().order_by('-creado_en')


class ContratoEOPDetailView(LoginRequiredMixin, DetailView):
    model = ContratoEOP
    template_name = "eop/contrato_detail.html"
    context_object_name = "contrato"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['hitos'] = self.object.hitos.all().order_by('id')
        return context


# =====================================================================
# ACTION VIEWS
# =====================================================================

class LiberarHitoActionView(LoginRequiredMixin, View):
    def post(self, request, pk):
        hito = get_object_or_404(EOPHitoEscrow, pk=pk)
        contrato_pk = hito.contrato.pk
        
        # En una app real, acá se leería la firma (ej. de un campo oculto del form o un header)
        # firma_ptf = request.POST.get('firma_ptf')
        
        try:
            EOPService.liberar_hito(hito.pk, firma_ptf=True) 
            messages.success(request, f"Hito '{hito.nombre}' liberado. Se generó la orden de pago.")
        except Exception as e:
            messages.error(request, f"Error al liberar hito: {str(e)}")
        
        return redirect('eop:contrato_detail', pk=contrato_pk)


# (Vista de fondeo manual eliminada; el fondeo ahora es por Webhook)


class AceptarContratoEOPActionView(LoginRequiredMixin, View):
    def post(self, request, pk):
        contrato = get_object_or_404(ContratoEOP, pk=pk)
        firma_tallerista_hex = request.POST.get('firma_hex', 'mocked_firma_hex_12345')
        
        try:
            # 1. El servicio en apps.eop sella el contrato con la firma del tallerista
            EOPService.firmar_contrato_tallerista(contrato, request.user, firma_tallerista_hex)
            
            messages.success(request, "Contrato firmado exitosamente. La MES ya fue notificada para activar el Timelock.")
        except Exception as e:
            messages.error(request, f"Error al firmar el contrato: {str(e)}")
            
        return redirect('eop:contrato_detail', pk=contrato.pk)


class CargarFacturaHitoActionView(LoginRequiredMixin, View):
    """
    Permite al tallerista subir el CAE/Nro de Factura en el Portal Tallerista
    para destrabar un hito que cayó en retención FISCAL_PENDING.
    """
    def post(self, request, pk):
        hito = get_object_or_404(EOPHitoEscrow, pk=pk)
        cae_factura = request.POST.get('cae_factura')
        
        if not cae_factura:
            messages.error(request, "Debe ingresar el número de CAE o Factura.")
            return redirect('eop:contrato_detail', pk=hito.contrato.pk)
            
        try:
            hito.factura_asociada_arca = cae_factura
            hito.save(update_fields=['factura_asociada_arca'])
            
            # Intentamos re-liberar el hito ahora que tiene factura
            EOPService.liberar_hito(hito.pk)
            messages.success(request, f"Factura {cae_factura} cargada. El hito ha sido liberado del Corralito Fiscal.")
        except Exception as e:
            messages.error(request, f"Error al procesar la factura: {str(e)}")
            
        # Nota: Idealmente redirigir al PortalTallerista, pero usamos detail por consistencia actual
        return redirect('eop:contrato_detail', pk=hito.contrato.pk)

# =====================================================================
# ENDPOINTS API FEDERADA (Recepción de Webhooks de la MES)
# =====================================================================

@method_decorator(csrf_exempt, name='dispatch')
class MESWebhookHitoLiberadoAPIView(View):
    """
    Endpoint que recibe el PUSH de la MES avisando que el Fideicomiso (FDI)
    ya pagó el hito, para que el ERP local pueda avanzar la producción.
    """
    def post(self, request, *args, **kwargs):
        # 1. Validar firma HMAC o Token de la MES para seguridad (omitido por brevedad)
        try:
            payload = json.loads(request.body)
            contrato_uuid = payload.get("contrato_uuid")
            hito_id = payload.get("hito_id")
            cae_arca = payload.get("cae_arca", None) # Por si la MES constató la factura
            
            contrato = ContratoEOP.objects.get(uuid_identificador=contrato_uuid)
            hito = contrato.hitos.get(id=hito_id)
            
            if hito.estado == "liberado":
                return JsonResponse({"status": "ok", "message": "Ya estaba liberado."})
                
            if cae_arca:
                hito.factura_asociada_arca = cae_arca
                hito.save(update_fields=["factura_asociada_arca"])
                
            # Forzamos la liberación saltando la validación del PTF (porque la MES ya lo validó)
            hito.estado = "liberado"
            hito.save(update_fields=["estado"])
            
            return JsonResponse({"status": "ok", "message": "Hito actualizado en nodo local."})
            
        except Exception as e:
            return JsonResponse({"status": "error", "error": str(e)}, status=400)
            

@method_decorator(csrf_exempt, name='dispatch')
class MESWebhookContratoFondeadoAPIView(View):
    """
    Endpoint que recibe el PUSH de la MES avisando que el Fideicomiso (FDI)
    adelantó el capital inicial (Hito Cero) por factoring.
    """
    def post(self, request, *args, **kwargs):
        try:
            payload = json.loads(request.body)
            contrato_uuid = payload.get("contrato_uuid")
            
            contrato = ContratoEOP.objects.get(uuid_identificador=contrato_uuid)
            
            # Ejecuta el cambio de estado de manera segura
            EOPService.fondear_escrow(contrato.id)
            
            return JsonResponse({"status": "ok", "message": "Contrato marcado como fondeado localmente."})
            
        except Exception as e:
            return JsonResponse({"status": "error", "error": str(e)}, status=400)
