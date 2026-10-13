import csv

from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse_lazy
from django.views.generic import DetailView, ListView, UpdateView

from .forms import EgresoEmpleadoForm
from .models import ConceptoLiquidacion, Empleado, LiquidacionNomina
from .services import NominaService


# ==========================================
# VISTAS DE REPORTES (LSD y Recibos)
# ==========================================

def exportar_lsd_csv(request, anio, mes):
    """
    Genera el archivo CSV (TXT format) para el Libro de Sueldos Digital AFIP (Registro 3).
    Formato simplificado para exportación.
    """
    liquidaciones = LiquidacionNomina.objects.filter(periodo_anio=anio, periodo_mes=mes)
    if not liquidaciones.exists():
        raise Http404("No hay liquidaciones para ese período.")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="LSD_Reg3_{anio}_{mes}.csv"'

    writer = csv.writer(response, delimiter=";")
    # Cabecera
    writer.writerow(["CUIL", "Codigo_AFIP", "Cantidad", "Monto"])

    for liq in liquidaciones:
        for det in liq.detalles.all():
            cod_afip = det.concepto.codigo_afip or det.concepto.codigo
            # Formato esperado: CUIL sin guiones
            cuil = liq.empleado.cuil.replace("-", "")
            writer.writerow(
                [cuil, cod_afip, f"{det.cantidad:.2f}", f"{det.subtotal:.2f}"]
            )

    return response


def imprimir_recibo(request, pk):
    """
    Renderiza el recibo de sueldo en HTML puro, listo para imprimir a PDF en el navegador.
    Utiliza un template similar al prototipo utils/nuevo_recibo_ley_bases.html
    """
    liquidacion = get_object_or_404(LiquidacionNomina, pk=pk)

    # Preparar datos para el gráfico
    neto = float(liquidacion.sueldo_neto_pagar)
    aportes = float(liquidacion.total_retenciones)
    contribuciones = float(liquidacion.total_cargas_patronales)

    # Separar detalles para la vista
    remunerativos = liquidacion.detalles.filter(concepto__tipo="REMUNERATIVO")
    no_remunerativos = liquidacion.detalles.filter(concepto__tipo="NO_REMUNERATIVO")
    retenciones = liquidacion.detalles.filter(concepto__tipo="RETENCION")
    patronales = liquidacion.detalles.filter(concepto__tipo="CONTRIBUCION")

    context = {
        "liq": liquidacion,
        "empleado": liquidacion.empleado,
        "remunerativos": remunerativos,
        "no_remunerativos": no_remunerativos,
        "retenciones": retenciones,
        "patronales": patronales,
        "chart_data": {
            "neto": neto,
            "aportes": aportes,
            "contribuciones": contribuciones,
        },
    }

    return render(request, "nomina/recibo.html", context)


# ==========================================
# VISTAS DE GESTIÓN DE EMPLEADOS (CBV)
# ==========================================

class EmpleadoListView(ListView):
    model = Empleado
    template_name = "nomina/empleado_list.html"
    context_object_name = "empleados"

    def get_queryset(self):
        # Por defecto muestra solo los activos, a menos que se filtre
        qs = super().get_queryset()
        if not self.request.GET.get("incluir_inactivos"):
            qs = qs.filter(activo=True)
        return qs


class EmpleadoDetailView(DetailView):
    model = Empleado
    template_name = "nomina/empleado_detail.html"
    context_object_name = "empleado"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Traemos el historial de liquidaciones del empleado
        context["liquidaciones"] = self.object.liquidaciones.order_by(
            "-periodo_anio", "-periodo_mes"
        )
        return context


class EmpleadoEgresoView(UpdateView):
    """
    Vista elegante para dar de baja a un empleado.
    Muestra un formulario específico (EgresoEmpleadoForm) que pide la fecha, el motivo,
    y tiene un checkbox para disparar la liquidación final automáticamente.
    """

    model = Empleado
    form_class = EgresoEmpleadoForm
    template_name = "nomina/empleado_egreso.html"

    def get_success_url(self):
        return reverse_lazy("nomina:empleado_detail", kwargs={"pk": self.object.pk})

    def form_valid(self, form):
        response = super().form_valid(form)
        empleado = self.object

        # El form guarda la fecha_egreso automáticamente por ser ModelForm, pero
        # necesitamos forzar inactivo y disparar la lógica.
        motivo = form.cleaned_data.get("motivo")
        generar_liq = form.cleaned_data.get("generar_liquidacion")

        if generar_liq and empleado.fecha_egreso:
            try:
                # El servicio se encarga de cambiar activo=False y generar la Liquidación Final
                liq_final = NominaService.liquidar_final(
                    empleado=empleado, fecha_egreso=empleado.fecha_egreso, motivo=motivo
                )
                messages.success(
                    self.request,
                    f"Egreso procesado. Se generó la Liquidación Final N° {liq_final.id} exitosamente.",
                )
            except Exception as e:
                messages.error(
                    self.request, f"Error al generar la liquidación final: {str(e)}"
                )
        else:
            # Si solo se quiso registrar la fecha sin liquidar
            empleado.activo = False
            empleado.save(update_fields=["activo"])
            messages.success(
                self.request,
                "El empleado fue dado de baja sin generar liquidación final.",
            )

        return response
