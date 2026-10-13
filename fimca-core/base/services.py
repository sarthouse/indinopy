from django.db import transaction
from django.utils import timezone
from django.apps import apps


class SecuenciaService:
    @staticmethod
    @transaction.atomic
    def obtener_siguiente_numero(codigo, fecha=None):
        if not fecha:
            fecha = timezone.now().date()

        Secuencia = apps.get_model('base', 'Secuencia')

        secuencia = (
            Secuencia.objects.select_for_update()
            .filter(codigo=codigo, activo=True)
            .first()
        )

        if not secuencia:
            # Fallback tolerante si no está inicializada la secuencia
            secuencia = Secuencia.objects.create(
                nombre=f"Secuencia {codigo}",
                codigo=codigo,
                siguiente_numero=1,
                longitud_relleno=6
            )

        numero_actual = secuencia.siguiente_numero
        secuencia.siguiente_numero += secuencia.incremento
        secuencia.save(update_fields=["siguiente_numero"])

        numero_str = str(numero_actual).zfill(secuencia.longitud_relleno)
        return f"{secuencia.prefijo}{numero_str}{secuencia.sufijo}"
