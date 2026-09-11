from django.db import transaction
from django.db.models import Sum
from decimal import Decimal
from django.core.exceptions import ValidationError
from .models import Asiento, Apunte, Cuenta, Diario

class ContabilidadService:
    """
    Servicio estricto para gestionar la Partida Doble.
    Ningún asiento puede pasar a estado 'asentado' si no cuadra perfectamente.
    """

    @staticmethod
    @transaction.atomic
    def crear_asiento(diario_codigo, fecha, descripcion, lineas_apuntes, documento_origen=None):
        """
        Crea un asiento y sus apuntes en estado borrador.
        lineas_apuntes: lista de diccionarios [{'cuenta_codigo': '1.1.01', 'debe': 100, 'haber': 0, 'contacto': obj}, ...]
        """
        diario = Diario.objects.get(codigo=diario_codigo)
        
        # Generar numero de asiento (Simplificado para el ERP)
        ultimo_asiento = Asiento.objects.filter(diario=diario, fecha__year=fecha.year).count()
        numero = f"AST-{diario.codigo}-{fecha.year}-{(ultimo_asiento + 1):06d}"

        asiento = Asiento.objects.create(
            numero=numero,
            fecha=fecha,
            descripcion=descripcion,
            diario=diario,
            estado='borrador'
        )

        if documento_origen:
            asiento.documento_origen = documento_origen
            asiento.save(update_fields=['content_type', 'object_id'])

        for linea in lineas_apuntes:
            cuenta = Cuenta.objects.get(codigo=linea['cuenta_codigo'])
            if not cuenta.imputable:
                raise ValidationError(f"La cuenta {cuenta.codigo} no es imputable. Es una cuenta agrupadora.")
            
            Apunte.objects.create(
                asiento=asiento,
                cuenta=cuenta,
                debe=Decimal(str(linea.get('debe', 0.00))),
                haber=Decimal(str(linea.get('haber', 0.00))),
                contacto=linea.get('contacto'),
                descripcion_linea=linea.get('descripcion_linea', '')
            )

        return asiento

    @staticmethod
    @transaction.atomic
    def validar_y_asentar(asiento_id):
        """
        Pasa un asiento de 'borrador' a 'asentado'.
        Aplica la regla fundamental de la Partida Doble: Suma del Debe == Suma del Haber.
        """
        asiento = Asiento.objects.select_for_update().get(id=asiento_id)
        
        if asiento.estado == 'asentado':
            return asiento # Ya estaba asentado
            
        if asiento.estado == 'anulado':
            raise ValidationError("No se puede asentar un asiento anulado.")

        totales = asiento.apuntes.aggregate(
            total_debe=Sum('debe'),
            total_haber=Sum('haber')
        )
        
        total_debe = totales['total_debe'] or Decimal('0.00')
        total_haber = totales['total_haber'] or Decimal('0.00')

        if total_debe != total_haber:
            raise ValidationError(
                f"Asiento Descuadrado (Partida Doble fallida). Debe: {total_debe} | Haber: {total_haber}. Diferencia: {total_debe - total_haber}"
            )
            
        if total_debe == Decimal('0.00'):
            raise ValidationError("El asiento no tiene montos registrados.")

        asiento.estado = 'asentado'
        asiento.save(update_fields=['estado'])
        
        return asiento
