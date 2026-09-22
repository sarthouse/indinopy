from decimal import Decimal
from rest_framework import serializers
from .models import NodoFederado
import nacl.signing
import nacl.exceptions
from django.utils.translation import gettext_lazy as _
import json

class NodoFederadoSerializer(serializers.ModelSerializer):
    class Meta:
        model = NodoFederado
        fields = ['id_nodo', 'nombre', 'tipo_nodo', 'url_base', 'clave_publica_nodo', 'activo', 'creado_en']
        read_only_fields = ['id_nodo', 'activo', 'creado_en']


class VerificacionFirmaMixin:
    """
    Mixin para validar firmas Ed25519 en los serializers.
    """
    def validar_firma_ed25519(self, payload_dict, firma_hex, clave_publica_hex):
        try:
            # Recreamos el payload canónico (JSON sin espacios, ordenado alfabéticamente)
            payload_bytes = json.dumps(payload_dict, separators=(',', ':'), sort_keys=True).encode('utf-8')
            verify_key = nacl.signing.VerifyKey(bytes.fromhex(clave_publica_hex))
            
            # La verificación arrojará una excepción si falla
            verify_key.verify(payload_bytes, bytes.fromhex(firma_hex))
            return True
        except (nacl.exceptions.BadSignatureError, ValueError, TypeError):
            return False


class EntradaEOPSerializer(serializers.Serializer, VerificacionFirmaMixin):
    """
    Serializer para recibir una nueva e-OP desde el Nodo de una Marca (Comitente).
    Soporta el sobre de transporte con payload canónico determinista y cronograma dinámico de hitos/etapas.
    """
    uuid_identificador = serializers.UUIDField()
    hash_seguridad = serializers.CharField(max_length=64)
    comitente_cuit = serializers.CharField(max_length=20)
    tallerista_cuit = serializers.CharField(max_length=20, required=False, allow_blank=True)
    monto_total_uci = serializers.DecimalField(max_digits=15, decimal_places=4)
    payload_canonico = serializers.JSONField()
    firma_comitente = serializers.CharField(max_length=128)
    clave_publica_comitente = serializers.CharField(max_length=64)
    cronograma_escrow_hitos = serializers.ListField(
        child=serializers.DictField(), required=False, allow_empty=True
    )

    def validate(self, data):
        # 1. Validar la firma matemática del JSON canónico
        if not self.validar_firma_ed25519(
            data['payload_canonico'], 
            data['firma_comitente'], 
            data['clave_publica_comitente']
        ):
            raise serializers.ValidationError(_("Firma criptográfica inválida o payload alterado."))
        
        # 2. Validar que la e-OP no exista ya en la MES (si este nodo es MES o tiene apps.mes)
        try:
            from apps.mes.models import RegistroEOP
            if RegistroEOP.objects.filter(uuid_identificador=data['uuid_identificador']).exists():
                raise serializers.ValidationError(_("Ya existe una e-OP con este UUID en la Red Federada."))
        except (ImportError, RuntimeError):
            pass

        # 3. Validar consistencia del cronograma de hitos si viene especificado
        hitos = data.get('cronograma_escrow_hitos') or data['payload_canonico'].get('cronograma_escrow_hitos')
        if hitos:
            total_porcentaje = sum(Decimal(str(h.get('porcentaje_tramo', 0))) for h in hitos)
            if abs(total_porcentaje - Decimal('100.00')) > Decimal('0.01'):
                raise serializers.ValidationError(_("La suma de porcentajes del cronograma de hitos debe ser exactamente 100%."))

        # 4. Validar mínimo obligatorio de 2 etapas productivas en el payload
        etapas = data['payload_canonico'].get('etapas_productivas', [])
        if len(etapas) < 2:
            raise serializers.ValidationError(_("Una e-OP federada requiere un mínimo obligatorio de dos etapas productivas."))
            
        return data


class FirmaEtapaSerializer(serializers.Serializer, VerificacionFirmaMixin):
    """
    Serializer para recibir la firma de aprobación de una etapa (Por Taller o PTF).
    """
    eop_uuid = serializers.UUIDField()
    etapa = serializers.CharField(max_length=50)
    actor_rol = serializers.ChoiceField(choices=[('tallerista', 'Tallerista'), ('ptf', 'PTF')])
    actor_cuit = serializers.CharField(max_length=11)
    firma_hex = serializers.CharField(max_length=128)
    clave_publica = serializers.CharField(max_length=64)
    coordenadas_gps = serializers.CharField(max_length=100, required=False, allow_blank=True) # Necesario si es PTF
    timestamp = serializers.DateTimeField()
    
    def validate(self, data):
        # El payload a verificar incluye uuid, etapa, cuit y timestamp
        payload_firma = {
            "eop_uuid": str(data['eop_uuid']),
            "etapa": data['etapa'],
            "actor_cuit": data['actor_cuit'],
            "timestamp": data['timestamp'].isoformat()
        }
        
        if data['actor_rol'] == 'ptf' and data.get('coordenadas_gps'):
            payload_firma["coordenadas_gps"] = data['coordenadas_gps']
            
        if not self.validar_firma_ed25519(
            payload_firma, 
            data['firma_hex'], 
            data['clave_publica']
        ):
            raise serializers.ValidationError(_("Firma Ed25519 del actor inválida."))
            
        return data
