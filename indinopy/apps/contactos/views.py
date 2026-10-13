from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import Contacto

class ContactoListView(LoginRequiredMixin, ListView):
    model = Contacto
    template_name = "contactos/contacto_list.html"
    context_object_name = "contactos"
    paginate_by = 30

    def get_queryset(self):
        return Contacto.objects.all().order_by('nombre')


class ContactoDetailView(LoginRequiredMixin, DetailView):
    model = Contacto
    template_name = "contactos/contacto_detail.html"
    context_object_name = "contacto"


class ContactoCreateView(LoginRequiredMixin, CreateView):
    model = Contacto
    template_name = "contactos/contacto_form.html"
    fields = ['nombre', 'cuil', 'email', 'telefono', 'direccion', 'tipo']
    
    def get_success_url(self):
        return reverse_lazy('contactos:contacto_detail', kwargs={'pk': self.object.pk})


class ContactoUpdateView(LoginRequiredMixin, UpdateView):
    model = Contacto
    template_name = "contactos/contacto_form.html"
    fields = ['nombre', 'cuil', 'email', 'telefono', 'direccion', 'tipo']
    
    def get_success_url(self):
        return reverse_lazy('contactos:contacto_detail', kwargs={'pk': self.object.pk})


# =====================================================================
# VISTAS DE AUTENTICACIÓN Y REGISTRO (PORTAL / SSR)
# =====================================================================
from django.contrib.auth import login as auth_login
from django.contrib.auth.views import LoginView, LogoutView
from django.views.generic import FormView
from django.shortcuts import redirect
from django.contrib import messages
from .auth_forms import StyledLoginForm, RegistroTalleristaForm


class LoginPortalView(LoginView):
    """
    Inicio de sesión para talleristas y operadores con interfaz Tailwind.
    """
    template_name = "auth/login.html"
    authentication_form = StyledLoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        messages.success(self.request, f"¡Bienvenido/a {form.get_user().first_name or form.get_user().username}!")
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "Usuario/CUIT o contraseña incorrectos.")
        return super().form_invalid(form)


class LogoutPortalView(LogoutView):
    """
    Cierre de sesión seguro con redirección al login.
    """
    next_page = reverse_lazy('login')

    def dispatch(self, request, *args, **kwargs):
        messages.info(request, "Sesión cerrada correctamente.")
        return super().dispatch(request, *args, **kwargs)


class RegistroTalleristaView(FormView):
    """
    Registro público de talleristas y façonniers e-OP.
    Crea el usuario y el contacto comercial de manera atómica e inicia sesión.
    """
    template_name = "auth/registro.html"
    form_class = RegistroTalleristaForm
    success_url = reverse_lazy('produccion:portal_tallerista')

    def form_valid(self, form):
        user, contacto = form.save()
        auth_login(self.request, user)
        messages.success(
            self.request,
            f"¡Registro completado exitosamente! Tu cuenta para '{contacto.nombre}' (CUIT {contacto.cuil}) "
            f"está lista para recibir e-OPs y emitir facturación asistida."
        )
        return redirect(self.success_url)

    def form_invalid(self, form):
        messages.error(self.request, "Por favor revise los errores señalados en el formulario.")
        return super().form_invalid(form)
