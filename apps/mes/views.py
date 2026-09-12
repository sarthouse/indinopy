from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import ListView, DetailView, View, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.shortcuts import get_object_or_404
from apps.contactos.models import Contacto

from .models import (
    RegistroEOP,
    ResolucionOP,
    AlertaColusion,
    TribunalArbitraje,
    ComisionCredito,
    PerfilPTF,
    LineaCreditoFDI,
)
from .services import PTFService


# =====================================================================
# GOBERNANZA — Panel de la Comisión de Crédito y Riesgo
# =====================================================================


class RegistroEOPListView(LoginRequiredMixin, ListView):
    """
    Panel principal de la MES: lista de todas las e-OPs en el Nodo.
    Incluye filtro por estado (en_revision, aprobado, vetado, en_disputa).
    """

    model = RegistroEOP
    template_name = "mes/eop_list.html"
    context_object_name = "registros"
    paginate_by = 30

    def get_queryset(self):
        qs = RegistroEOP.objects.all().order_by("timelock_vencimiento")
        estado = self.request.GET.get("estado")
        if estado:
            qs = qs.filter(estado=estado)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from django.utils import timezone

        # Destacar e-OPs con Timelock próximo a vencer (próximas 6 horas)
        context["proximas_a_vencer"] = RegistroEOP.objects.filter(
            estado="en_revision",
            timelock_vencimiento__lte=timezone.now() + timezone.timedelta(hours=6),
        ).count()
        return context


class RegistroEOPDetailView(LoginRequiredMixin, DetailView):
    """
    Detalle de una e-OP en el Nodo MES: hash, firmas, resoluciones y estado del Timelock.
    """

    model = RegistroEOP
    template_name = "mes/eop_detail.html"
    context_object_name = "registro"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["resoluciones"] = self.object.resoluciones.all().order_by("creado_en")
        context["arbitrajes"] = self.object.casos_arbitraje.all()
        return context


class AlertaColusionListView(LoginRequiredMixin, ListView):
    """
    Lista de alertas de posibles Talleres Espejo (fragmentación artificial).
    Generadas automáticamente por el worker de Celery.
    """

    model = AlertaColusion
    template_name = "mes/alertas_colusion.html"
    context_object_name = "alertas"
    paginate_by = 20

    def get_queryset(self):
        return AlertaColusion.objects.filter(estado_investigacion="pendiente").order_by(
            "-creado_en"
        )


class TribunalArbitrajeListView(LoginRequiredMixin, ListView):
    model = TribunalArbitraje
    template_name = "mes/tribunal_list.html"
    context_object_name = "casos"
    paginate_by = 20

    def get_queryset(self):
        return TribunalArbitraje.objects.exclude(estado="laudado").order_by(
            "fecha_limite_laudo"
        )


class TribunalArbitrajeDetailView(LoginRequiredMixin, DetailView):
    model = TribunalArbitraje
    template_name = "mes/tribunal_detail.html"
    context_object_name = "caso"


# =====================================================================
# GESTIÓN DE PTFs — Panel de la Comisión
# =====================================================================


class PTFListView(LoginRequiredMixin, ListView):
    """
    Lista de todos los PTFs registrados: activos, con credencial vencida, revocados.
    """

    model = PerfilPTF
    template_name = "mes/ptf_list.html"
    context_object_name = "ptfs"
    paginate_by = 20

    def get_queryset(self):
        return PerfilPTF.objects.select_related("usuario", "comision").order_by(
            "-ucp_score_ptf"
        )


class PTFDetailView(LoginRequiredMixin, DetailView):
    """
    Ficha completa del PTF: credencial, zona de cobertura, historial de auditorías.
    """

    model = PerfilPTF
    template_name = "mes/ptf_detail.html"
    context_object_name = "ptf"


# =====================================================================
# PORTAL DEL PTF — Vistas que usa el PTF en campo
# =====================================================================


class PTFPortalView(LoginRequiredMixin, ListView):
    """
    Dashboard personal del PTF: e-OPs pendientes en su zona, estadísticas.
    Solo muestra las e-OPs dentro de la zona de cobertura del PTF logueado.
    """

    template_name = "mes/ptf_portal.html"
    context_object_name = "pendientes"

    def get_queryset(self):
        try:
            perfil = self.request.user.perfil_ptf
        except PerfilPTF.DoesNotExist:
            return RegistroEOP.objects.none()

        # Solo e-OPs en revisión y cuyo tallerista esté en la zona del PTF
        # TODO: Filtrar por zona_cobertura PostGIS cuando haya datos geográficos
        return RegistroEOP.objects.filter(estado="en_revision").order_by(
            "timelock_vencimiento"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            context["perfil_ptf"] = self.request.user.perfil_ptf
        except PerfilPTF.DoesNotExist:
            context["perfil_ptf"] = None
        return context


class RegistrarClavePublicaActionView(LoginRequiredMixin, View):
    """
    El PTF sube su clave pública Ed25519 (generada en su dispositivo via WebCrypto API).
    La clave privada NUNCA llega al servidor.
    """

    def post(self, request):
        clave_publica_hex = request.POST.get("clave_publica_hex", "").strip()

        try:
            perfil = request.user.perfil_ptf
        except PerfilPTF.DoesNotExist:
            messages.error(request, "No tenés un Perfil PTF asignado.")
            return redirect("mes:ptf_portal")

        try:
            PTFService.registrar_clave_publica(perfil, clave_publica_hex)
            messages.success(
                request,
                "Clave pública registrada exitosamente. Tu certificado digital fue emitido.",
            )
        except Exception as e:
            messages.error(request, f"Error al registrar la clave: {str(e)}")

        return redirect("mes:ptf_detail", pk=perfil.pk)


class AprobarEOPActionView(LoginRequiredMixin, View):
    """
    El PTF aprueba una e-OP en campo.
    Recibe: UUID de la e-OP, firma_hex, coordenadas GPS.
    """

    def post(self, request, uuid):
        try:
            perfil = request.user.perfil_ptf
        except PerfilPTF.DoesNotExist:
            messages.error(request, "No tenés un Perfil PTF activo.")
            return redirect("mes:eop_list")

        firma_hex = request.POST.get("firma_hex", "").strip()
        lat = request.POST.get("lat")
        lon = request.POST.get("lon")

        gps_point = None
        if lat and lon:
            from django.contrib.gis.geos import Point

            try:
                gps_point = Point(float(lon), float(lat), srid=4326)
            except (ValueError, TypeError):
                messages.error(request, "Coordenadas GPS inválidas.")
                return redirect("mes:eop_detail", pk=uuid)

        try:
            PTFService.aprobar_eop(uuid, perfil, firma_hex, gps_point)
            messages.success(request, f"e-OP {uuid} aprobada. Escrow liberado.")
        except Exception as e:
            messages.error(request, f"Error al aprobar la e-OP: {str(e)}")

        return redirect("mes:eop_detail", pk=uuid)


class VetarEOPActionView(LoginRequiredMixin, View):
    """
    El PTF o un miembro de la Comisión veta una e-OP durante el Timelock.
    Abre automáticamente un caso en el TribunalArbitraje.
    """

    def post(self, request, uuid):
        try:
            perfil = request.user.perfil_ptf
        except PerfilPTF.DoesNotExist:
            messages.error(request, "No tenés un Perfil PTF activo.")
            return redirect("mes:eop_list")

        fundamento = request.POST.get("fundamento", "").strip()
        if not fundamento:
            messages.error(request, "El fundamento del veto es obligatorio.")
            return redirect("mes:eop_detail", pk=uuid)

        try:
            PTFService.vetar_eop(uuid, perfil, fundamento)
            messages.warning(
                request,
                f"e-OP {uuid} vetada. Se abrió un caso en el Tribunal de Arbitraje (72h).",
            )
        except Exception as e:
            messages.error(request, f"Error al vetar la e-OP: {str(e)}")

        return redirect("mes:eop_detail", pk=uuid)


# =====================================================================
# ACTION VIEWS — Administración de PTFs (por la Comisión)
# =====================================================================


class RevocarPTFActionView(LoginRequiredMixin, View):
    """
    La ComisionCredito revoca la credencial de un PTF.
    En Fase 4 notificará a todos los nodos de la red.
    """

    def post(self, request, pk):
        ptf = get_object_or_404(PerfilPTF, pk=pk)
        motivo = request.POST.get("motivo", "").strip()

        try:
            PTFService.revocar_ptf(ptf, motivo=motivo)
            messages.warning(request, f"Credencial del PTF {ptf} revocada.")
        except Exception as e:
            messages.error(request, f"Error al revocar el PTF: {str(e)}")

        return redirect("mes:ptf_detail", pk=pk)


# =====================================================================
# API FEDERADA — Consulta de Cupo de Crédito (Pull desde Marcas)
# =====================================================================


class EstadoCreditoFDIAPIView(APIView):
    """
    Endpoint para que un nodo Marca consulte su límite de crédito disponible.
    Requiere que el CUIT de la marca venga en el header X-CUIT.
    """

    def get(self, request, *args, **kwargs):
        cuit_marca = request.headers.get("X-CUIT")
        if not cuit_marca:
            return Response(
                {"error": "Header X-CUIT requerido"}, status=status.HTTP_400_BAD_REQUEST
            )

        # En el nodo MES, buscamos a la marca en nuestra tabla de Contactos
        contacto = get_object_or_404(Contacto, cuit=cuit_marca)

        # Buscamos su línea de crédito
        try:
            linea = contacto.linea_credito_mes
        except LineaCreditoFDI.DoesNotExist:
            return Response(
                {"error": "La marca no tiene línea de crédito homologada en la MES"},
                status=status.HTTP_404_NOT_FOUND,
            )

        cupo_disponible = linea.limite_otorgado - linea.deuda_viva

        return Response(
            {
                "cuit_marca": cuit_marca,
                "limite_otorgado": float(linea.limite_otorgado),
                "deuda_viva_fdi": float(linea.deuda_viva),
                "mora_activa": linea.mora_activa,
                "cupo_disponible": float(cupo_disponible)
                if cupo_disponible > 0
                else 0.0,
            }
        )
