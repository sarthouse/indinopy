from decimal import Decimal
from django.contrib.gis.geos import Point
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import ListView, DetailView, View, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from base.models import Contacto

from .models import (
    RegistroEOP,
    ResolucionOP,
    AlertaColusion,
    TribunalArbitraje,
    ComisionCredito,
    PerfilPTF,
    LineaCreditoFDI,
    Denuncia,
    VotacionComision,
    VotoComision,
)
from .services import PTFService, ComisionService, DenunciaService


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
    slug_field = "uuid_identificador"
    slug_url_kwarg = "uuid"

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
            try:
                gps_point = Point(float(lon), float(lat), srid=4326)
            except (ValueError, TypeError):
                messages.error(request, "Coordenadas GPS inválidas.")
                return redirect("mes:eop_detail", uuid=uuid)

        try:
            PTFService.aprobar_eop(uuid, perfil, firma_hex, gps_point)
            messages.success(request, f"e-OP {uuid} aprobada. Escrow liberado.")
        except Exception as e:
            messages.error(request, f"Error al aprobar la e-OP: {str(e)}")

        return redirect("mes:eop_detail", uuid=uuid)


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
            return redirect("mes:eop_detail", uuid=uuid)

        try:
            PTFService.vetar_eop(uuid, perfil, fundamento)
            messages.warning(
                request,
                f"e-OP {uuid} vetada. Se abrió un caso en el Tribunal de Arbitraje (72h).",
            )
        except Exception as e:
            messages.error(request, f"Error al vetar la e-OP: {str(e)}")

        return redirect("mes:eop_detail", uuid=uuid)


# =====================================================================
# ACTION VIEWS — Administración de PTFs (por la Comisión)
# =====================================================================


class RevocarPTFActionView(LoginRequiredMixin, View):
    """
    La ComisionCredito revoca la credencial de un PTF y notifica a los nodos federados.
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

        # En el nodo MES, buscamos a la marca en Contactos
        contacto = get_object_or_404(Contacto, cuil=cuit_marca)

        from .models import EvaluacionTrayectoriaSETP
        from .services import SETPService
        from .serializers import EstadoCreditoFDISerializer

        evaluacion = EvaluacionTrayectoriaSETP.objects.filter(cuit_evaluado=cuit_marca).first()
        if not evaluacion:
            evaluacion = SETPService.obtener_o_crear_perfil(cuit=cuit_marca, tipo_actor="comitente")

        serializer = EstadoCreditoFDISerializer(evaluacion)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ParametrosArancelariosFDIAPIView(APIView):
    """
    Endpoint público federado para que los nodos ERP consulten las alícuotas
    vigentes de micro-canon de red MES y fondo de riesgo FDI (Dossier FIMCA).
    """

    def get(self, request, *args, **kwargs):
        # Alícuotas institucionales oficiales aprobadas por la Comisión de Crédito
        from .models import PautaEscrowMES
        from .serializers import ParametrosArancelariosSerializer

        pauta = PautaEscrowMES.objects.filter(activa=True).first()
        resolucion = pauta.resolucion_arancel if pauta else "RES-MES-2026-01"
        alicuota_canon_mes = pauta.alicuota_canon_mes if pauta else Decimal("0.0100")
        alicuota_fondo_fdi = pauta.alicuota_fondo_fdi if pauta else Decimal("0.0050")
        alicuota_stock = pauta.alicuota_stock if pauta else Decimal("0.0050")
        alicuota_total = alicuota_canon_mes + alicuota_fondo_fdi

        data = {
            "version_arancel": resolucion,
            "alicuota_canon_mes": str(alicuota_canon_mes),
            "alicuota_fondo_riesgo_fdi": str(alicuota_fondo_fdi),
            "alicuota_total_recargo": str(alicuota_total),
            "alicuota_stock": str(alicuota_stock),
            "descripcion": f"Resolución {resolucion}: Recargo MES/FDI ({alicuota_total * 100}% s/MOD) y Stock ({alicuota_stock * 100}% s/BOM)",
        }
        serializer = ParametrosArancelariosSerializer(data)
        return Response(serializer.data, status=status.HTTP_200_OK)


# =====================================================================
# GOBERNANZA — Votaciones de la Comisión y Denuncias
# =====================================================================

class EmitirVotoActionView(LoginRequiredMixin, View):
    """
    Un miembro de la Comisión emite su voto sobre un asunto.
    """
    def post(self, request, votacion_id):
        aprueba = request.POST.get("aprueba") == "true"
        fundamento = request.POST.get("fundamento", "")
        firma_hex = request.POST.get("firma_hex", "")
        
        # Obtenemos el MiembroComision vinculado al usuario logueado
        # asumiendo que User tiene una relacion 1 a 1 con MiembroComision
        if not hasattr(request.user, "miembro_comision"):
            messages.error(request, "No sos miembro de la Comisión de Crédito.")
            return redirect("mes:eop_list")
            
        try:
            ComisionService.emitir_voto(
                votacion_id=votacion_id,
                miembro_id=request.user.miembro_comision.id,
                aprueba=aprueba,
                fundamento=fundamento,
                firma_hex=firma_hex
            )
            messages.success(request, "Voto registrado exitosamente.")
        except Exception as e:
            messages.error(request, f"Error al emitir voto: {str(e)}")
            
        return redirect("mes:eop_list")

class RadicarDenunciaActionView(LoginRequiredMixin, View):
    """
    Un tallerista radica una denuncia contra una marca o funcionario.
    Gatilla la inmunidad de oficio y el congelamiento preventivo.
    """
    def post(self, request):
        denunciado_id = request.POST.get("denunciado_id")
        motivo = request.POST.get("motivo")
        descripcion = request.POST.get("descripcion")
        
        # El denunciante es el Contacto vinculado al usuario (Tallerista)
        if not hasattr(request.user, "contacto"):
            messages.error(request, "Solo los talleristas registrados pueden denunciar.")
            return redirect("mes:eop_list")
            
        denunciante = request.user.contacto
        denunciado = get_object_or_404(Contacto, pk=denunciado_id)
        
        try:
            denuncia = DenunciaService.radicar_denuncia(
                denunciante=denunciante,
                denunciado=denunciado,
                motivo=motivo,
                descripcion=descripcion,
                evidencia_digital=[] # Podría venir de archivos en el request
            )
            messages.success(request, f"Denuncia {denuncia.id} radicada. Tenés Inmunidad Fiscal por 180 días.")
        except Exception as e:
            messages.error(request, f"Error al procesar la denuncia: {str(e)}")

        return redirect("mes:eop_list")


# =====================================================================
# PORTAL FIDUCIARIO — Clearing y Liquidación de Escrow (FDI / BAPRO)
# =====================================================================


class DashboardFiduciarioView(LoginRequiredMixin, ListView):
    """
    Dashboard del Fideicomiso (FDI) para monitorear hitos de escrow liberados,
    generar lotes batch de clearing bancario y conciliar pagos.
    """
    template_name = "mes/fiduciaria/clearing_dashboard.html"
    context_object_name = "hitos_pendientes"

    def get_queryset(self):
        from .services import ClearingBancarioService
        return ClearingBancarioService.obtener_hitos_pendientes_clearing()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cotizacion = Decimal("1.00")
        context["cotizacion_uci"] = cotizacion

        # Totales proyectados
        total_centavos = 0
        for hito in context["hitos_pendientes"]:
            monto_ars = getattr(hito, "monto_ars", Decimal("0.00"))
            total_centavos += int(monto_ars * 100)
        context["monto_total_ars"] = Decimal(total_centavos) / Decimal("100.00")
        return context


class EjecutarClearingBatchActionView(LoginRequiredMixin, View):
    """
    Gatilla la liquidación manual o descarga del lote batch de clearing desde la UI.
    """
    def post(self, request):
        from .services import ClearingBancarioService
        hitos_ids = request.POST.getlist("hitos_seleccionados")
        if not hitos_ids:
            messages.warning(request, "No seleccionaste ningún hito para liquidar.")
            return redirect("mes:fiduciaria_dashboard")

        lote_ref = f"LOTE-MANUAL-{timezone.now().strftime('%Y%m%d%H%M')}"
        resultado = ClearingBancarioService.procesar_callback_clearing(
            lote_referencia=lote_ref,
            hitos_ids=[int(hid) for hid in hitos_ids],
            estado_pago="EXITOSO",
        )
        messages.success(
            request,
            f"Lote {lote_ref} liquidado exitosamente: {resultado.get('procesados', 0)} órdenes de pago fiduciario generadas."
        )
        return redirect("mes:fiduciaria_dashboard")


# =====================================================================
# GOBERNANZA — SETP y Diligencia Debida
# =====================================================================


class SETPMiCalificacionAPIView(APIView):
    """
    Endpoint de Habeas Data y Scoring SETP (Art. 16° Ley e-OP).
    Permite a comitentes y talleres auditar su calificación, historial de mora y cupo operativo.
    """
    def get(self, request):
        cuit = request.GET.get("cuit")
        if not cuit:
            return Response({"error": "Debe proporcionar el parámetro 'cuit'."}, status=status.HTTP_400_BAD_REQUEST)

        from .models import EvaluacionTrayectoriaSETP
        from .services import SETPService
        from .serializers import SETPMiCalificacionSerializer

        evaluacion = EvaluacionTrayectoriaSETP.objects.filter(cuit_evaluado=cuit).first()
        if not evaluacion:
            evaluacion = SETPService.obtener_o_crear_perfil(cuit=cuit)

        serializer = SETPMiCalificacionSerializer(evaluacion)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ConsultaCDDAPIView(APIView):
    """
    Endpoint de constatación pública/federada de Certificado de Diligencia Debida (Art. 22° Ley e-OP).
    Acredita vigencia del Puerto Seguro Laboral frente a AFIP/ARCA o el fuero laboral.
    """
    def get(self, request):
        eop_uuid = request.GET.get("eop_uuid")
        periodo = request.GET.get("periodo")
        if not eop_uuid:
            return Response({"error": "Debe indicar 'eop_uuid'."}, status=status.HTTP_400_BAD_REQUEST)

        from .models import CertificadoDiligenciaDebida
        from .serializers import CertificadoDiligenciaDebidaSerializer

        qs = CertificadoDiligenciaDebida.objects.filter(eop_asociada__uuid_identificador=eop_uuid).select_related("eop_asociada", "tallerista", "comitente")
        if periodo:
            qs = qs.filter(periodo_mes_anio=periodo)

        cdd = qs.first()
        if not cdd:
            return Response({"error": "No se halló certificado de diligencia debida para los parámetros indicados."}, status=status.HTTP_404_NOT_FOUND)

        serializer = CertificadoDiligenciaDebidaSerializer(cdd)
        return Response(serializer.data, status=status.HTTP_200_OK)


# =====================================================================
# MERCADO DE CAPITALES, TITULIZACIÓN BIP Y RESERVAS (FDI)
# =====================================================================

class CarterasBIPAPIView(APIView):
    """
    API para consulta y conformación de Carteras Titulizables de e-OPs (Art. 17° Ley e-OP).
    Permite a los administradores del Fondo empaquetar e-OPs activas para colocación en ALyCs.
    """
    def get(self, request):
        from .models import CarteraTitulizableBIP
        from .serializers import CarteraTitulizableBIPSerializer

        estado = request.GET.get("estado")
        qs = CarteraTitulizableBIP.objects.all().prefetch_related("contratos").order_by("-creado_en")
        if estado:
            qs = qs.filter(estado=estado)

        serializer = CarteraTitulizableBIPSerializer(qs, many=True)
        return Response({"total": len(serializer.data), "carteras": serializer.data}, status=status.HTTP_200_OK)

    def post(self, request):
        from .services import TitulizacionBIPService
        from .serializers import ConformarCarteraBIPInputSerializer

        input_serializer = ConformarCarteraBIPInputSerializer(data=request.data)
        if not input_serializer.is_valid():
            return Response(input_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        datos = input_serializer.validated_data
        try:
            cartera = TitulizacionBIPService.conformar_cartera_bip(
                codigo_cartera=datos["codigo_cartera"],
                eop_uuids=datos["eop_uuids"],
                descripcion=datos.get("descripcion", ""),
            )
            return Response({
                "status": "cartera_conformada",
                "id": cartera.id,
                "codigo_cartera": cartera.codigo_cartera,
                "monto_nominal_uci": str(cartera.monto_nominal_total_uci),
                "contratos_empaquetados": cartera.contratos.count(),
            }, status=status.HTTP_201_CREATED)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class SeriesBonoBIPAPIView(APIView):
    """
    API pública y de colocación para Series de Bonos BIP (CNV RG 917/2021).
    Permite consultar títulos vigentes en el mercado secundario o emitir una nueva serie.
    """
    def get(self, request):
        from .models import SerieBonoBIP
        from .serializers import SerieBonoBIPSerializer

        moneda = request.GET.get("moneda")
        qs = SerieBonoBIP.objects.filter(estado="vigente").select_related("cartera_subyacente").order_by("-fecha_emision")
        if moneda:
            qs = qs.filter(moneda=moneda)

        serializer = SerieBonoBIPSerializer(qs, many=True)
        return Response({"total": len(serializer.data), "series_vigentes": serializer.data}, status=status.HTTP_200_OK)

    def post(self, request):
        from .services import TitulizacionBIPService
        from .serializers import EmitirBonoBIPInputSerializer

        input_serializer = EmitirBonoBIPInputSerializer(data=request.data)
        if not input_serializer.is_valid():
            return Response(input_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        datos = input_serializer.validated_data
        try:
            serie = TitulizacionBIPService.emitir_serie_bono_bip(
                cartera_id=datos["cartera_id"],
                codigo_ticker=datos["codigo_ticker"],
                plazo_dias=datos["plazo_dias"],
                moneda=datos["moneda"],
                tasa_tna=datos["tasa_interes_anual"],
                revisor_cnv=datos.get("revisor_externo_cnv", "Calificadora de Riesgo SVS / CNV"),
            )
            return Response({
                "status": "serie_bip_emitida",
                "ticker": serie.codigo_ticker,
                "monto_nominal": str(serie.monto_emision_nominal),
                "moneda": serie.moneda,
                "vencimiento": serie.fecha_vencimiento.isoformat(),
                "etiqueta_svs": serie.es_etiqueta_svs,
            }, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class SubcuentasReservaFDIAPIView(APIView):
    """
    Endpoint de supervisión de las 4 Subcuentas de Reserva Fiduciarias del Fondo (Art. 16° Ley e-OP).
    Permite auditar el estado patrimonial y cobertura de siniestros/moras.
    """
    def get(self, request):
        from .models import SubcuentaReservaFondo
        from .services import FDISubcuentasReservaService
        from .serializers import SubcuentaReservaFondoSerializer

        FDISubcuentasReservaService.inicializar_subcuentas_estatutarias()
        subcuentas = SubcuentaReservaFondo.objects.all().order_by("id")
        serializer = SubcuentaReservaFondoSerializer(subcuentas, many=True)
        return Response({"subcuentas_reserva": serializer.data}, status=status.HTTP_200_OK)


class PolizaStockActivaAPIView(APIView):
    """
    Endpoint de constatación de la Póliza Colectiva de Stock en Custodia (Art. 20° bis Ley e-OP).
    Invocado para verificar cobertura aseguradora previa a la liberación del Hito Cero.
    """
    def get(self, request):
        from .models import PolizaColectivaStock
        from .serializers import PolizaColectivaStockSerializer

        poliza = PolizaColectivaStock.objects.filter(activa=True).order_by("-fecha_vigencia_hasta").first()
        if not poliza:
            return Response({
                "cobertura_activa": False,
                "mensaje": "No hay póliza colectiva de stock vigente en el Fondo."
            }, status=status.HTTP_200_OK)

        serializer = PolizaColectivaStockSerializer(poliza)
        return Response(serializer.data, status=status.HTTP_200_OK)


