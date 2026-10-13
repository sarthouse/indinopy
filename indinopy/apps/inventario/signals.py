from django.db.models.signals import post_migrate
from django.dispatch import receiver
from .models import UnidadMedida

@receiver(post_migrate)
def crear_unidades_medida_por_defecto(sender, **kwargs):
    """Crea las unidades de medida base del sistema industrial al migrar."""
    if sender.name == "apps.inventario":

        unidades_defecto = [
            {"nombre": "Unidades", "simbolo": "u", "tipo": "unidad"},
            {"nombre": "Pares", "simbolo": "par", "tipo": "unidad"},
            {"nombre": "Metros", "simbolo": "m", "tipo": "longitud"},
            {"nombre": "Centímetros", "simbolo": "cm", "tipo": "longitud"},
            {"nombre": "Kilogramos", "simbolo": "kg", "tipo": "peso"},
            {"nombre": "Gramos", "simbolo": "g", "tipo": "peso"},
            {"nombre": "Litros", "simbolo": "l", "tipo": "volumen"},
            {"nombre": "Horas", "simbolo": "hs", "tipo": "tiempo"},
            {"nombre": "Minutos", "simbolo": "min", "tipo": "tiempo"},
        ]

        for u in unidades_defecto:
            UnidadMedida.objects.get_or_create(
                simbolo=u["simbolo"],
                defaults={"nombre": u["nombre"], "tipo": u["tipo"], "activa": True},
            )
