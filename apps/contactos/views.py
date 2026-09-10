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
    fields = ['nombre', 'tipo_documento', 'numero_documento', 'email', 'telefono', 'direccion', 'es_cliente', 'es_proveedor', 'es_taller_homologado']
    
    def get_success_url(self):
        return reverse_lazy('contactos:contacto_detail', kwargs={'pk': self.object.pk})


class ContactoUpdateView(LoginRequiredMixin, UpdateView):
    model = Contacto
    template_name = "contactos/contacto_form.html"
    fields = ['nombre', 'tipo_documento', 'numero_documento', 'email', 'telefono', 'direccion', 'es_cliente', 'es_proveedor', 'es_taller_homologado']
    
    def get_success_url(self):
        return reverse_lazy('contactos:contacto_detail', kwargs={'pk': self.object.pk})
