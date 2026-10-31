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
    firma_tallerista = serializers.CharField(max_length=128, required=False, allow_blank=True)
    cronograma_escrow_hitos = serializers.ListField(
        child=serializers.DictField(), required=False, allow_empty=True
    )

    def validate(self, data):
        # 1. Validar la firma matemática del JSON canónico por el comitente
        if not self.validar_firma_ed25519(
            data['payload_canonico'], 
            data['firma_comitente'], 
            data['clave_publica_comitente']
        ):
            raise serializers.ValidationError(_("Firma criptográfica inválida o payload alterado."))

        # 2. Validar que la e-OP cuente con la firma digital del tallerista gestor
        firma_tallerista = data.get('firma_tallerista') or data['payload_canonico'].get('firmas_digitales', {}).get('tallerista', {}).get('firma_hex')
        if not firma_tallerista:
            raise serializers.ValidationError(
                _("La e-OP no puede ser aceptada en la Red Federada sin la firma digital del tallerista gestor.")
            )
        
        # 3. Validar que la e-OP no exista ya registrada en la MES
        try:
            from fdi.models import RegistroEOP
            if RegistroEOP.objects.filter(uuid_identificador=data['uuid_identificador']).exists():
                raise serializers.ValidationError(_("Ya existe una e-OP con este UUID registrada en el Nodo MES."))
        except (ImportError, RuntimeError):
            pass

        # 4. Validar cláusula obligatoria de confesión de deuda Hito Cero (Art. 6° Ley e-OP)
        clausula_h0 = data['payload_canonico'].get('clausula_confesion_deuda_h0')
        if clausula_h0 is not True:
            raise serializers.ValidationError({
                "error": "CLAUSULA_CONFESION_H0_REQUERIDA",
                "detalle": _(
                    "La e-OP debe contener expresamente la cláusula de confesión irrevocable de deuda líquida y exigible "
                    "para el Hito Cero conforme al Art. 6° del Anteproyecto de Ley e-OP."
                )
            })

        # 5. Validar consistencia del cronograma de hitos si viene especificado
        hitos = data.get('cronograma_escrow_hitos') or data['payload_canonico'].get('cronograma_escrow_hitos')
        if hitos:
            total_porcentaje = sum(Decimal(str(h.get('porcentaje_tramo', 0))) for h in hitos)
            if abs(total_porcentaje - Decimal('100.00')) > Decimal('0.01'):
                raise serializers.ValidationError(_("La suma de porcentajes del cronograma de hitos debe ser exactamente 100%."))

        # 6. Validar consistencia matemática de la alícuota del canon FDI/MES y monto exigible (Art. 4° inc. 4 Ley e-OP)
        vector_costos = data['payload_canonico'].get('vector_costos', {})
        mod_val = Decimal(str(vector_costos.get('mod_servicios', vector_costos.get('mod', data['monto_total_uci']))))
        bom_val = Decimal(str(vector_costos.get('insumos_bom', vector_costos.get('bom', '0.00'))))
        fdi_val = Decimal(str(vector_costos.get('canon_fdi_mes', vector_costos.get('fdi', '0.00'))))

        # Alícuotas máximas legales:
        # Canon Operativo s/MOD: 1.5% (0.015). Cobertura Stock s/BOM: 0.5% (0.005)
        canon_operativo = Decimal(str(vector_costos.get('canon_fdi_operativo', mod_val * Decimal('0.015')))).quantize(Decimal('0.01'))
        canon_stock = Decimal(str(vector_costos.get('canon_fdi_stock', bom_val * Decimal('0.005')))).quantize(Decimal('0.01'))

        # Si se declaró canon_fdi_mes unificado o desglosado:
        # El canon fiduciario s/MOD no puede superar el 1.5%
        fdi_operativo_esperado = (mod_val * Decimal("0.015")).quantize(Decimal("0.01"))
        diferencia_operativa = abs(canon_operativo - fdi_operativo_esperado)

        # Si viene solo canon_fdi_mes consolidado sin desglosar
        if "canon_fdi_operativo" not in vector_costos:
            fdi_esperado_total = fdi_operativo_esperado + (bom_val * Decimal("0.005")).quantize(Decimal("0.01"))
            diferencia_total = abs(fdi_val - fdi_operativo_esperado)
            diferencia_con_stock = abs(fdi_val - fdi_esperado_total)
            diferencia = min(diferencia_total, diferencia_con_stock)
        else:
            diferencia = diferencia_operativa

        # Tolerancia máxima de 5 centavos por redondeos intermedios
        if diferencia > Decimal("0.05"):
            raise serializers.ValidationError({
                "error": "ALICUOTA_DESACTUALIZADA",
                "alicuota_vigente": "0.015",
                "costo_mod": str(mod_val),
                "costo_fdi_recibido": str(fdi_val),
                "costo_fdi_esperado": str(fdi_operativo_esperado),
                "detalle": _(
                    "El canon FDI/MES declarado no coincide con los parámetros arancelarios vigentes (máx 1.5% s/MOD). "
                    "Actualice los aranceles en el nodo emisor y regenere la e-OP con las firmas correspondientes."
                )
            })

        # 7. Validar que el monto exigible excluya los insumos provistos (BOM s/Art. 4° inc 4.b)
        canon_total = canon_operativo + canon_stock
        monto_esperado_uci = mod_val + canon_total
        if abs(data['monto_total_uci'] - monto_esperado_uci) > Decimal("0.05"):
            raise serializers.ValidationError({
                "error": "MONTO_EXIGIBLE_INVALIDO",
                "monto_total_uci": str(data['monto_total_uci']),
                "monto_esperado_uci": str(monto_esperado_uci),
                "detalle": _(
                    "El monto total exigible de la e-OP debe ser exactamente igual a MOD + Canones FDI. "
                    "El valor de insumos provistos (BOM) se encuentra bajo régimen de custodia/depósito "
                    "y no puede integrar la deuda exigible (Art. 4° inc 4.b Ley e-OP)."
                )
            })

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
