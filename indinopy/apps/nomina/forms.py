from django import forms
from django.utils.translation import gettext_lazy as _
from .models import Empleado

class EgresoEmpleadoForm(forms.ModelForm):
    MOTIVOS_EGRESO = [
        ('RENUNCIA', 'Renuncia'),
        ('DESPIDO_SIN_CAUSA', 'Despido sin Justa Causa'),
        ('DESPIDO_CON_CAUSA', 'Despido con Justa Causa'),
        ('MUTUO_ACUERDO', 'Mutuo Acuerdo (Art. 241)'),
        ('FIN_CONTRATO', 'Fin de Contrato a Plazo Fijo'),
    ]
    
    motivo = forms.ChoiceField(choices=MOTIVOS_EGRESO, label="Motivo de Egreso")
    generar_liquidacion = forms.BooleanField(
        required=False, 
        initial=True, 
        label="Generar Liquidación Final Automáticamente",
        help_text="Si está marcado, el sistema calculará las indemnizaciones y proporcionales."
    )

    class Meta:
        model = Empleado
        fields = ['fecha_egreso']
        widgets = {
            'fecha_egreso': forms.DateInput(attrs={'type': 'date', 'class': 'form-input'})
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['fecha_egreso'].required = True
