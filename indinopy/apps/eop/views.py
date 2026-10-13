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
        contrato = self.object
        context['hitos'] = contrato.hitos.all().order_by('id')
        context['incidencias_jit'] = contrato.incidencias_jit.all().order_by('-creado_en')
        
        from apps.eop.services import UCIService
        cotizacion_uci = UCIService.obtener_cotizacion_actual() or Decimal("1.00")
        context['cotizacion_uci'] = cotizacion_uci

        # Cálculo de Mano de Obra en ARS y Crédito Fiscal Presunto 10% (Art. 23.1 Ley e-OP)
        monto_mod_ars = round(contrato.costo_mod * cotizacion_uci, 2)
        credito_presunto_10 = round(monto_mod_ars * Decimal("0.10"), 2)
        
        context['monto_mod_ars'] = monto_mod_ars
        context['credito_fiscal_presunto_10'] = credito_presunto_10
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
            
            messages.success(
                request, 
                f"¡Contrato e-OP #{contrato.numero or contrato.id} firmado exitosamente! "
                f"FDI notificado: Timelock fiduciario de 48h iniciado. El Hito Cero se liberará al expirar el plazo."
            )
        except Exception as e:
            messages.error(request, f"Error al firmar el contrato: {str(e)}")
            
        return redirect('eop:contrato_detail', pk=contrato.pk)


class CargarFacturaHitoActionView(LoginRequiredMixin, View):
    """
    Permite al tallerista subir el CAE/Nro de Factura en el Portal Tallerista
    para destrabar un hito que cayó en retención de cierre fiscal.
    Valida opcionalmente los datos fiscales con el Web Service de Constatación (WSCDC).
    """
    def post(self, request, pk):
        from apps.afip.services import FacturacionAsistidaService
        hito = get_object_or_404(EOPHitoEscrow, pk=pk)
        cae_factura = request.POST.get('cae_factura', '').strip()
        pto_vta = request.POST.get('pto_vta')
        cbte_nro = request.POST.get('cbte_nro')
        cbte_fch = request.POST.get('cbte_fch')
        imp_total = request.POST.get('imp_total')
        
        if not cae_factura:
            messages.error(request, "Debe ingresar el código de CAE o número de autorización otorgado por ARCA.")
            return redirect('eop:contrato_detail', pk=hito.contrato.pk)

        # Si el usuario ingresó los metadatos completos del comprobante, constatamos ante ARCA
        if pto_vta and cbte_nro and cbte_fch and imp_total:
            try:
                contrato = hito.contrato
                cuit_emisor = ""
                if contrato.ptf_asignado:
                    cuit_emisor = contrato.ptf_asignado.cuil or contrato.ptf_asignado.cuit or ""
                
                constatacion = FacturacionAsistidaService.constatar_factura_externa(
                    cuit_emisor=cuit_emisor,
                    pto_vta=int(pto_vta),
                    cbte_tipo=11,  # Factura C
                    cbte_nro=int(cbte_nro),
                    cbte_fch=cbte_fch.replace("-", ""),
                    imp_total=float(imp_total),
                    cae=cae_factura,
                )
                if constatacion.get("resultado") != "A":
                    motivos = ", ".join(constatacion.get("observaciones", ["Comprobante no válido"]))
                    messages.warning(
                        request,
                        f"ARCA no pudo constatar el comprobante de forma directa: {motivos}. "
                        f"Se registró el CAE bajo revisión fiduciaria."
                    )
                else:
                    messages.info(
                        request,
                        f"Comprobante {int(pto_vta):04d}-{int(cbte_nro):08d} validado y constatado exitosamente ante ARCA (WSCDC)."
                    )
            except Exception as wscdc_err:
                messages.warning(request, f"Aviso de verificación ARCA: {str(wscdc_err)}")
            
        try:
            hito.factura_asociada_arca = cae_factura
            hito.save(update_fields=['factura_asociada_arca'])
            
            # Intentamos re-liberar el hito ahora que tiene factura
            EOPService.liberar_hito(hito.pk)
            messages.success(
                request, 
                f"Factura CAE {cae_factura} vinculada exitosamente. "
                f"El Hito '{hito.nombre}' fue liberado de la Retención de Cierre Fiscal (RCF)."
            )
        except Exception as e:
            messages.error(request, f"Error al procesar la liberación del hito: {str(e)}")
            
        return redirect('eop:contrato_detail', pk=hito.contrato.pk)


class EmitirFacturaAsistidaActionView(LoginRequiredMixin, View):
    """
    Emite en 1-Click la Factura C asistida para el hito retenido en RCF
    aplicando la retención previsional SIPA del 2% (Art. 24.5 Ley e-OP)
    y gestionando los mensajes al usuario.
    """
    def post(self, request, pk):
        from apps.afip.services import FacturacionAsistidaService
        hito = get_object_or_404(EOPHitoEscrow, pk=pk)
        punto_venta = int(request.POST.get('punto_venta', 1))

        try:
            resultado = FacturacionAsistidaService.confirmar_y_emitir_factura_asistida(
                hito_id=hito.id,
                punto_venta=punto_venta,
            )
            messages.success(
                request,
                f"¡Factura C asistida emitida con éxito ante ARCA! "
                f"CAE: {resultado['cae']}. Retención SIPA 2%: ${resultado['retencion_sipa_ars']:.2f}. "
                f"Hito liberado automáticamente."
            )
        except Exception as exc:
            messages.error(
                request,
                f"Error al emitir factura asistida ante ARCA: {str(exc)}"
            )

        return redirect('eop:contrato_detail', pk=hito.contrato.pk)


# =====================================================================
# ENDPOINTS API FEDERADA (Recepción de Webhooks del FDI)
# =====================================================================

@method_decorator(csrf_exempt, name='dispatch')
class FDIWebhookHitoLiberadoAPIView(View):
    """
    Endpoint que recibe el PUSH del FDI avisando que el Fideicomiso
    ya pagó el hito, para que el ERP local pueda avanzar la producción.
    """
    def post(self, request, *args, **kwargs):
        try:
            payload = json.loads(request.body)
            contrato_uuid = payload.get("contrato_uuid")
            hito_id = payload.get("hito_id")
            cae_arca = payload.get("cae_arca", None)
            
            contrato = ContratoEOP.objects.get(uuid_identificador=contrato_uuid)
            hito = contrato.hitos.get(id=hito_id)
            
            if hito.estado == "liberado":
                return JsonResponse({"status": "ok", "message": "Ya estaba liberado."})
                
            if cae_arca:
                hito.factura_asociada_arca = cae_arca
                hito.save(update_fields=["factura_asociada_arca"])
                
            hito.estado = "liberado"
            hito.save(update_fields=["estado"])
            
            return JsonResponse({"status": "ok", "message": "Hito actualizado en nodo local."})
            
        except Exception as e:
            return JsonResponse({"status": "error", "error": str(e)}, status=400)


MESWebhookHitoLiberadoAPIView = FDIWebhookHitoLiberadoAPIView


@method_decorator(csrf_exempt, name='dispatch')
class FDIWebhookContratoFondeadoAPIView(View):
    """
    Endpoint que recibe el PUSH del FDI avisando que el Fideicomiso
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


MESWebhookContratoFondeadoAPIView = FDIWebhookContratoFondeadoAPIView
