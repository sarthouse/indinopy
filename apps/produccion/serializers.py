from rest_framework import serializers
from .models import OrdenProduccion
from apps.contactos.models import Contacto

class OrdenProduccionHeadlessSerializer(serializers.ModelSerializer):
    tallerista_cuit = serializers.CharField(write_only=True, max_length=11)
    
    class Meta:
        model = OrdenProduccion
        fields = [
            'id', 'numero', 'tallerista_cuit', 'bom_headless', 
            'cantidad_total', 'es_eop_federada'
        ]
        read_only_fields = ['id', 'numero']

    def validate_tallerista_cuit(self, value):
        # En modo headless, se pasa el CUIT del tallerista, 
        # necesitamos convertirlo internamente al Contacto Tallerista
        try:
            return Contacto.objects.get(cuil=value)
        except Contacto.DoesNotExist:
            # En un caso real, podríamos crearlo on-the-fly, pero por seguridad exigimos que exista
            raise serializers.ValidationError("No existe un tallerista registrado con ese CUIT.")
    
    def create(self, validated_data):
        # Mapeamos tallerista_cuit a la asignación (asumimos que la OP necesita un tallerista asignado)
        # La OrdenProduccion real se vincula al tallerista a través de OPAsignacion, 
        # pero para el gateway guardamos la instancia de OP.
        
        tallerista = validated_data.pop('tallerista_cuit')
        
        # Generar número automáticamente si no está seteado
        from apps.base.models import generar_numero_documento
        if not validated_data.get('numero'):
            validated_data['numero'] = generar_numero_documento("EOP")
            
        op = OrdenProduccion.objects.create(
            tipo="fason", # Headless usualmente manda a fasón externo
            **validated_data
        )
        
        # (Acá internamente se crearía la asignación `OPAsignacion` al tallerista)
        return op
