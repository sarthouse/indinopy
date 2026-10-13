import json
from decimal import Decimal
import nacl.signing
import nacl.exceptions
from rest_framework import serializers
from django.utils.translation import gettext_lazy as _


class VerificacionFirmaMixin:
    """
    Mixin para validar firmas Ed25519 en los serializers.
    """
    def validar_firma_ed25519(self, payload_dict, firma_hex, clave_publica_hex):
        try:
            payload_bytes = json.dumps(payload_dict, separators=(',', ':'), sort_keys=True).encode('utf-8')
            verify_key = nacl.signing.VerifyKey(bytes.fromhex(clave_publica_hex))
            verify_key.verify(payload_bytes, bytes.fromhex(firma_hex))
            return True
        except (nacl.exceptions.BadSignatureError, ValueError, TypeError):
            return False


class EntradaEOPSerializer(serializers.Serializer, VerificacionFirmaMixin):
    """
    Serializer del sobre de transporte e-OP para interoperabilidad con la red FIMCA.
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

        # 3. Validar consistencia del cronograma de hitos si viene especificado
        hitos = data.get('cronograma_escrow_hitos') or data['payload_canonico'].get('cronograma_escrow_hitos')
        if hitos:
            total_porcentaje = sum(Decimal(str(h.get('porcentaje_tramo', 0))) for h in hitos)
            if abs(total_porcentaje - Decimal('100.00')) > Decimal('0.01'):
                raise serializers.ValidationError(_("La suma de porcentajes del cronograma de hitos debe ser exactamente 100%."))

        # 4. Validar consistencia matemática de la alícuota del canon FDI/MES (Art. 4° inc. 4 Ley e-OP)
        vector_costos = data['payload_canonico'].get('vector_costos', {})
        mod_val = Decimal(str(vector_costos.get('mod_servicios', vector_costos.get('mod', data['monto_total_uci']))))
        bom_val = Decimal(str(vector_costos.get('insumos_bom', vector_costos.get('bom', '0.00'))))
        fdi_val = Decimal(str(vector_costos.get('canon_fdi_mes', vector_costos.get('fdi', '0.00'))))

        canon_operativo = Decimal(str(vector_costos.get('canon_fdi_operativo', mod_val * Decimal('0.015')))).quantize(Decimal('0.01'))
        fdi_operativo_esperado = (mod_val * Decimal("0.015")).quantize(Decimal("0.01"))
        diferencia_operativa = abs(canon_operativo - fdi_operativo_esperado)

        if "canon_fdi_operativo" not in vector_costos:
            fdi_esperado_total = fdi_operativo_esperado + (bom_val * Decimal("0.005")).quantize(Decimal("0.01"))
            diferencia_total = abs(fdi_val - fdi_operativo_esperado)
            diferencia_con_stock = abs(fdi_val - fdi_esperado_total)
            diferencia = min(diferencia_total, diferencia_con_stock)
        else:
            diferencia = diferencia_operativa

        if diferencia > Decimal("0.05"):
            raise serializers.ValidationError({
                "error": "ALICUOTA_DESACTUALIZADA",
                "alicuota_vigente": "0.015",
                "costo_mod": str(mod_val),
                "costo_fdi_recibido": str(fdi_val),
                "costo_fdi_esperado": str(fdi_operativo_esperado),
                "detalle": _(
                    "El canon FDI/MES declarado no coincide con los parámetros arancelarios vigentes (máx 1.5% s/MOD)."
                )
            })

        return data
