from django.shortcuts import redirect, render
from django.views.generic import View
from django.contrib.auth.mixins import LoginRequiredMixin


class HomeIndexView(LoginRequiredMixin, View):
    """
    Punto de entrada principal tras el login:
    - Si el usuario es un Tallerista/Façonnier externo, va directo a su portal especial.
    - Si es un usuario interno/staff, accede al Dashboard general del ERP.
    """
    def get(self, request):
        user = request.user
        # Tallerista externo
        if hasattr(user, 'perfil_contacto') and not user.is_staff:
            return redirect('produccion:portal_tallerista')

        # Usuario interno / Staff: Dashboard del ERP
        return render(request, "dashboard/index.html", {
            "usuario": user,
        })
