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
            raise ValueError(f"No existe una secuencia activa configurada para el código '{codigo}'.")
            
        if secuencia.ultimo_reinicio:
            if secuencia.reinicio_anual and secuencia.ultimo_reinicio.year != fecha.year:
                secuencia.siguiente_numero = 1
                secuencia.ultimo_reinicio = fecha
            elif secuencia.reinicio_mensual and (
                secuencia.ultimo_reinicio.year != fecha.year
                or secuencia.ultimo_reinicio.month != fecha.month
            ):
                secuencia.siguiente_numero = 1
                secuencia.ultimo_reinicio = fecha
        else:
            secuencia.ultimo_reinicio = fecha
            
        numero_actual = secuencia.siguiente_numero
        secuencia.siguiente_numero += secuencia.incremento
        secuencia.save(update_fields=["siguiente_numero", "ultimo_reinicio"])
        
        contexto_fecha = {
            "year": fecha.strftime("%Y"),
            "month": fecha.strftime("%m"),
            "day": fecha.strftime("%d"),
            "puntoventa": str(secuencia.punto_venta).zfill(5) if secuencia.punto_venta else "00000"
        }
        
        try:
            prefijo = secuencia.prefijo % contexto_fecha if "%" in secuencia.prefijo else secuencia.prefijo
        except (ValueError, TypeError, KeyError):
            prefijo = secuencia.prefijo
            
        try:
            sufijo = secuencia.sufijo % contexto_fecha if "%" in secuencia.sufijo else secuencia.sufijo
        except (ValueError, TypeError, KeyError):
            sufijo = secuencia.sufijo
            
        numero_str = str(numero_actual).zfill(secuencia.longitud_relleno)
        return f"{prefijo}{numero_str}{sufijo}"
