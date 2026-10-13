import re
from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.contactos.models import Contacto


class StyledLoginForm(AuthenticationForm):
    """
    Formulario de Login estilizado con Tailwind CSS.
    """
    username = forms.CharField(
        label=_("Usuario o CUIT"),
        widget=forms.TextInput(
            attrs={
                "class": "w-full px-4 py-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:ring-2 focus:ring-sky-500 focus:border-transparent outline-none transition text-sm",
                "placeholder": "ej. 20384759281 o usuario",
                "autocomplete": "username",
            }
        ),
    )
    password = forms.CharField(
        label=_("Contraseña"),
        widget=forms.PasswordInput(
            attrs={
                "class": "w-full px-4 py-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:ring-2 focus:ring-sky-500 focus:border-transparent outline-none transition text-sm",
                "placeholder": "••••••••",
                "autocomplete": "current-password",
            }
        ),
    )


class RegistroTalleristaForm(forms.Form):
    """
    Formulario público de registro para Talleristas / Façonniers e-OP.
    Crea el auth.User y su Contacto asociado con perfil de Fabricante/Tallerista.
    """
    cuit = forms.CharField(
        label=_("CUIT / CUIL"),
        max_length=13,
        help_text=_("11 dígitos sin guiones"),
        widget=forms.TextInput(
            attrs={
                "class": "w-full px-4 py-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:ring-2 focus:ring-sky-500 focus:border-transparent outline-none transition text-sm",
                "placeholder": "20384958371",
            }
        ),
    )
    razon_social = forms.CharField(
        label=_("Nombre del Taller o Razón Social"),
        max_length=200,
        widget=forms.TextInput(
            attrs={
                "class": "w-full px-4 py-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:ring-2 focus:ring-sky-500 focus:border-transparent outline-none transition text-sm",
                "placeholder": "Taller Confecciones del Sur",
            }
        ),
    )
    email = forms.EmailField(
        label=_("Correo Electrónico"),
        widget=forms.EmailInput(
            attrs={
                "class": "w-full px-4 py-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:ring-2 focus:ring-sky-500 focus:border-transparent outline-none transition text-sm",
                "placeholder": "contacto@taller.com",
            }
        ),
    )
    telefono = forms.CharField(
        label=_("Teléfono / WhatsApp"),
        max_length=50,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "w-full px-4 py-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:ring-2 focus:ring-sky-500 focus:border-transparent outline-none transition text-sm",
                "placeholder": "+54 9 11 1234-5678",
            }
        ),
    )
    direccion = forms.CharField(
        label=_("Dirección del Taller"),
        max_length=300,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "w-full px-4 py-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:ring-2 focus:ring-sky-500 focus:border-transparent outline-none transition text-sm",
                "placeholder": "Av. San Martín 1234, Ramos Mejía",
            }
        ),
    )
    password = forms.CharField(
        label=_("Contraseña"),
        widget=forms.PasswordInput(
            attrs={
                "class": "w-full px-4 py-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:ring-2 focus:ring-sky-500 focus:border-transparent outline-none transition text-sm",
                "placeholder": "Al menos 8 caracteres",
            }
        ),
    )
    password_confirm = forms.CharField(
        label=_("Confirmar Contraseña"),
        widget=forms.PasswordInput(
            attrs={
                "class": "w-full px-4 py-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:ring-2 focus:ring-sky-500 focus:border-transparent outline-none transition text-sm",
                "placeholder": "Repite la contraseña",
            }
        ),
    )

    def clean_cuit(self):
        cuit = re.sub(r"\D", "", self.cleaned_data.get("cuit", ""))
        if len(cuit) != 11:
            raise ValidationError(_("El CUIT debe tener exactamente 11 dígitos."))
        if User.objects.filter(username=cuit).exists():
            raise ValidationError(_("Ya existe un usuario registrado con este CUIT."))
        return cuit

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get("password")
        p2 = cleaned_data.get("password_confirm")
        if p1 and p2 and p1 != p2:
            self.add_error("password_confirm", _("Las contraseñas no coinciden."))
        if p1 and len(p1) < 8:
            self.add_error("password", _("La contraseña debe tener al menos 8 caracteres."))
        return cleaned_data

    @transaction.atomic
    def save(self):
        cuit = self.cleaned_data["cuit"]
        razon_social = self.cleaned_data["razon_social"]
        email = self.cleaned_data["email"]
        password = self.cleaned_data["password"]
        telefono = self.cleaned_data.get("telefono", "")
        direccion = self.cleaned_data.get("direccion", "")

        # 1. Crear el usuario del sistema con username = CUIT
        user = User.objects.create_user(
            username=cuit,
            email=email,
            password=password,
            first_name=razon_social[:30],
        )

        # 2. Crear o asociar el Contacto de tipo fabricante/tallerista
        codigo_contacto = f"TAL-{cuit[-4:]}"
        # Si el código ya existe por coincidencia de últimos 4 dígitos, buscamos único
        counter = 1
        base_codigo = codigo_contacto
        while Contacto.objects.filter(codigo=codigo_contacto).exists():
            codigo_contacto = f"{base_codigo}-{counter}"
            counter += 1

        contacto = Contacto.objects.create(
            usuario_asociado=user,
            nombre=razon_social,
            codigo=codigo_contacto,
            tipo="fabricante",
            cuil=cuit,
            condicion_iva="monotributista",
            email=email,
            telefono=telefono,
            direccion=direccion,
            es_taller_homologado=False,
        )

        return user, contacto
