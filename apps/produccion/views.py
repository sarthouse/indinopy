from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import ListView, DetailView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from .models import (
    OrdenProduccion,
    OPEtapaTracking,
    OPParteProduccion,
    OPParteProduccionLinea,
)
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

# =====================================================================
# PORTAL DE PROVEEDORES / TALLERISTAS EXTERNOS
# =====================================================================

class PortalTalleristaListView(LoginRequiredMixin, ListView):
    """
    Portal web para el operario/tallerista que no tiene servidor propio.
    Ve únicamente los lotes/etapas que la Marca le asignó a su Contacto.
    """
    model = OPEtapaTracking
    template_name = "produccion/portal_tallerista_list.html"
    context_object_name = "etapas_asignadas"
    
    def get_queryset(self):
        # Filtramos por las etapas asignadas a su contacto
        if not hasattr(self.request.user, 'perfil_contacto'):
            return OPEtapaTracking.objects.none()
            
        contacto_usuario = self.request.user.perfil_contacto
        return OPEtapaTracking.objects.filter(
            tallerista_asignado=contacto_usuario, 
            estado__in=['pendiente', 'en_curso']
        )

class DeclararParteActionView(LoginRequiredMixin, View):
    """
    Permite al tallerista declarar un avance físico de producción desde su celular.
    """
    @transaction.atomic
    def post(self, request, tracking_id):
        etapa = get_object_or_404(OPEtapaTracking, pk=tracking_id)
        
        # Validar permisos: solo el tallerista asignado puede declarar
        if not hasattr(request.user, 'perfil_contacto') or etapa.tallerista_asignado != request.user.perfil_contacto:
            raise PermissionDenied("No tienes permisos para declarar avances en esta etapa.")
        
        cantidad_terminada = request.POST.get('cantidad', 0)
        
        try:
            # Crear el parte físico
            parte = OPParteProduccion.objects.create(
                op=etapa.op,
                etapa_tracking=etapa,
                numero_parte=f"WEB-{etapa.id}",
                responsable=request.user
            )
            
            # (Simplificación) Impactamos la primera variación de la OP
            variacion = etapa.op.variaciones.first()
            if variacion:
                OPParteProduccionLinea.objects.create(
                    parte=parte,
                    variacion=variacion,
                    cantidad_primera=cantidad_terminada
                )
                variacion.cantidad_producida += int(cantidad_terminada)
                variacion.save()

            messages.success(request, f"¡Excelente! Declaraste {cantidad_terminada} pares terminados.")
        except Exception as e:
            messages.error(request, f"Ocurrió un error al guardar el avance: {str(e)}")
            
        return redirect('produccion:portal_tallerista')
