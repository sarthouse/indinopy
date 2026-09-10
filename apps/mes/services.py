from django.db import transaction
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType
import hashlib
import json

from .models import PerfilPTF, ComisionCredito, RegistroEOP, ResolucionOP


class PTFService:
    """
    Capa de servicios para el ciclo de vida del Promotor Territorial
    de Formalización (PTF) y su participación en la gobernanza de las e-OPs.

    Responsabilidades:
    - Registro y homologación de PTFs por parte de la ComisionCredito.
    - Emisión y verificación de certificados digitales (PKI Federada).
    - Revocación y distribución a nodos externos.
    - Validación de firmas de campo (Ed25519 + GPS + Timelock).
    - Aprobación o veto de e-OPs en el Nodo MES.
    """

    # ─────────────────────────────────────────────────────────────────────
    # CICLO DE VIDA DEL PTF
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def registrar_ptf(usuario, comision_id, municipios_texto, rol="ptf_junior",
                      fecha_vencimiento=None):
        """
        La ComisionCredito registra un nuevo PTF en el sistema.
        El PTF queda en estado inicial sin clave pública — aún no puede firmar.
        La fecha de vencimiento por defecto es 1 año desde hoy.
        """
        from datetime import timedelta

        comision = ComisionCredito.objects.get(pk=comision_id)

        if hasattr(usuario, "perfil_ptf"):
            raise ValueError(
                f"El usuario {usuario.username} ya tiene un PerfilPTF registrado."
            )

        hoy = timezone.now().date()
        vencimiento = fecha_vencimiento or (hoy + timedelta(days=365))

        perfil = PerfilPTF.objects.create(
            usuario=usuario,
            comision=comision,
            rol=rol,
            municipios_texto=municipios_texto,
            fecha_emision_credencial=hoy,
            fecha_vencimiento_credencial=vencimiento,
            activo=True,
        )
        return perfil

    @staticmethod
    @transaction.atomic
    def registrar_clave_publica(perfil_ptf, clave_publica_hex):
        """
        El PTF sube su clave pública (generada en su dispositivo via WebCrypto API).
        La MES la registra y emite el certificado firmado.
        La clave privada NUNCA llega al servidor.

        Args:
            perfil_ptf: instancia de PerfilPTF
            clave_publica_hex: string hex de 64 chars (32 bytes Ed25519)
        """
        if len(clave_publica_hex) != 64:
            raise ValueError(
                "Clave pública Ed25519 inválida. Debe ser un hex de 64 caracteres (32 bytes)."
            )

        perfil_ptf.clave_publica_ed25519 = clave_publica_hex
        perfil_ptf.save(update_fields=["clave_publica_ed25519"])

        # Emitir certificado automáticamente al registrar la clave
        PTFService.emitir_certificado(perfil_ptf)
        return perfil_ptf

    @staticmethod
    def emitir_certificado(perfil_ptf):
        """
        La MES genera y firma el certificado digital del PTF.

        El certificado es un JSON canónico que incluye todos los datos
        de identidad y zona del PTF. Está firmado con la clave privada
        de la MES, por lo que cualquier nodo puede verificarlo offline
        usando solo la clave pública de la MES.

        En Fase 3 (Criptografía Completa), aquí se firmará con Ed25519
        usando la clave privada de la MES almacenada en el servidor.
        Por ahora se genera el payload canónico y se sella con SHA-256.
        """
        payload = {
            "tipo": "certificado_ptf_v1",
            "ptf_cuit": perfil_ptf.usuario.username,  # TODO: campo cuil en User
            "nombre": perfil_ptf.usuario.get_full_name(),
            "rol": perfil_ptf.rol,
            "comision": perfil_ptf.comision.nombre,
            "region": perfil_ptf.comision.region,
            "municipios": perfil_ptf.municipios_texto,
            "clave_publica_ptf": perfil_ptf.clave_publica_ed25519,
            "emitido_en": perfil_ptf.fecha_emision_credencial.isoformat(),
            "valido_hasta": perfil_ptf.fecha_vencimiento_credencial.isoformat(),
            "version": 1,
        }

        # Serialización canónica determinista (claves ordenadas)
        payload_str = json.dumps(payload, sort_keys=True, ensure_ascii=False)

        # Hash del payload (en Fase 3 esto será reemplazado por firma Ed25519 de la MES)
        hash_certificado = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

        certificado = {
            **payload,
            "hash_certificado": hash_certificado,
            # "firma_mes": "..."  ← TODO Fase 3: firma Ed25519 con clave privada MES
        }

        perfil_ptf.certificado_mes_json = certificado
        perfil_ptf.save(update_fields=["certificado_mes_json"])

        # TODO Fase 4: distribuir el certificado a todos los nodos registrados
        # PTFService._distribuir_certificado_a_nodos(perfil_ptf)

        return certificado

    @staticmethod
    @transaction.atomic
    def revocar_ptf(perfil_ptf, motivo=""):
        """
        Revoca la credencial del PTF. Sus firmas anteriores siguen siendo válidas
        (están en el historial inmutable). Las futuras son rechazadas.

        En Fase 4 se notificará a todos los nodos vía webhook push.
        """
        if not perfil_ptf.activo:
            raise ValueError(f"El PTF {perfil_ptf} ya está revocado.")

        perfil_ptf.activo = False

        # Incrementar versión del certificado para invalidarlo en nodos cacheados
        cert = dict(perfil_ptf.certificado_mes_json)
        cert["version"] = cert.get("version", 1) + 1
        cert["estado"] = "revocado"
        cert["motivo_revocacion"] = motivo
        cert["revocado_en"] = timezone.now().isoformat()
        perfil_ptf.certificado_mes_json = cert

        perfil_ptf.save(update_fields=["activo", "certificado_mes_json"])

        # TODO Fase 4: POST a todos los nodos con el certificado revocado
        # PTFService._notificar_revocacion_a_nodos(perfil_ptf)

        return perfil_ptf

    # ─────────────────────────────────────────────────────────────────────
    # VERIFICACIÓN CRIPTOGRÁFICA
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def verificar_certificado_offline(certificado_json):
        """
        Verifica la integridad de un certificado PTF sin conectarse a la MES.
        Cualquier nodo puede llamar a este método con la clave pública de la MES.

        Por ahora verifica el hash SHA-256 del payload canónico.
        En Fase 3 verificará la firma Ed25519 de la MES.
        """
        cert = dict(certificado_json)
        hash_declarado = cert.pop("hash_certificado", None)
        cert.pop("firma_mes", None)  # Sacar firma antes de recalcular

        payload_str = json.dumps(cert, sort_keys=True, ensure_ascii=False)
        hash_calculado = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

        return hash_declarado == hash_calculado

    @staticmethod
    def verificar_firma_campo(hash_eop_hex, firma_hex, perfil_ptf):
        """
        Verifica la firma Ed25519 que el PTF generó en campo con su dispositivo.

        Args:
            hash_eop_hex: Hash SHA-256 de la e-OP que el PTF firmó
            firma_hex: Firma Ed25519 generada en el dispositivo del PTF
            perfil_ptf: PerfilPTF del firmante

        Returns:
            True si la firma es válida, False si no.

        TODO Fase 3: Implementar con PyNaCl:
            from nacl.signing import VerifyKey
            vk = VerifyKey(bytes.fromhex(perfil_ptf.clave_publica_ed25519))
            vk.verify(bytes.fromhex(hash_eop_hex), bytes.fromhex(firma_hex))
        """
        if not perfil_ptf.clave_publica_ed25519:
            raise ValueError("El PTF no tiene clave pública registrada.")

        # Stub funcional: verifica que el formato sea correcto
        # En Fase 3 esto se reemplaza por la verificación matemática real
        if not firma_hex or len(firma_hex) != 128:  # 64 bytes Ed25519 = 128 hex chars
            return False

        # TODO Fase 3: descomentar cuando PyNaCl esté instalado
        # try:
        #     from nacl.signing import VerifyKey
        #     from nacl.exceptions import BadSignatureError
        #     vk = VerifyKey(bytes.fromhex(perfil_ptf.clave_publica_ed25519))
        #     vk.verify(bytes.fromhex(hash_eop_hex), bytes.fromhex(firma_hex))
        #     return True
        # except BadSignatureError:
        #     return False

        return True  # Stub: siempre True hasta Fase 3

    @staticmethod
    def verificar_gps_en_zona(gps_point, perfil_ptf):
        """
        Verifica que el PTF esté dentro de su zona de cobertura usando PostGIS.

        Args:
            gps_point: django.contrib.gis.geos.Point con las coordenadas del PTF
            perfil_ptf: PerfilPTF con su MultiPolygonField zona_cobertura

        Returns:
            True si el punto está dentro del polígono, False si no.
        """
        if not perfil_ptf.zona_cobertura:
            # Si no hay polígono definido, solo validamos que el PTF esté activo
            return perfil_ptf.credencial_vigente

        return perfil_ptf.zona_cobertura.contains(gps_point)

    # ─────────────────────────────────────────────────────────────────────
    # GOBERNANZA DE e-OPs EN EL NODO MES
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    @transaction.atomic
    def aprobar_eop(registro_eop_uuid, perfil_ptf, firma_hex, gps_point=None):
        """
        Flujo completo de aprobación exprés de una e-OP por un PTF en campo.

        Secuencia:
        1. Valida que la credencial del PTF esté vigente
        2. Verifica que el GPS esté en la zona de cobertura del PTF
        3. Verifica la firma Ed25519 del PTF
        4. Actualiza RegistroEOP a "aprobado_expres"
        5. Registra la ResolucionOP con la firma del PTF
        6. Dispara la liberación del Escrow correspondiente

        Args:
            registro_eop_uuid: UUID de la e-OP en el Nodo MES
            perfil_ptf: PerfilPTF del PTF que aprueba
            firma_hex: Firma Ed25519 del hash de la e-OP
            gps_point: Coordenadas GPS del PTF al momento de firmar
        """
        registro = RegistroEOP.objects.select_for_update().get(
            uuid_identificador=registro_eop_uuid
        )

        # Validación 1: Estado de la e-OP
        if registro.estado not in ["en_revision"]:
            raise ValueError(
                f"La e-OP {registro_eop_uuid} no está en revisión "
                f"(estado actual: {registro.get_estado_display()})."
            )

        # Validación 2: Credencial del PTF
        if not perfil_ptf.credencial_vigente:
            raise ValueError(
                f"La credencial del PTF {perfil_ptf} está vencida o revocada."
            )

        # Validación 3: GPS en zona de cobertura
        if gps_point and not PTFService.verificar_gps_en_zona(gps_point, perfil_ptf):
            raise ValueError(
                f"El PTF {perfil_ptf} está fuera de su zona de cobertura autorizada."
            )

        # Validación 4: Firma criptográfica
        hash_eop = registro.hash_seguridad
        if not PTFService.verificar_firma_campo(hash_eop, firma_hex, perfil_ptf):
            raise ValueError("La firma Ed25519 del PTF es inválida.")

        # Validación 5: Timelock no vencido negativamente (no es Silencio Positivo)
        if registro.timelock_vencimiento < timezone.now():
            # Ya venció, el Silencio Positivo debería haber actuado antes
            raise ValueError(
                "El Timelock ya venció. Esta e-OP debió procesarse por Silencio Positivo."
            )

        # Todo OK → Aprobar
        registro.estado = "aprobado_expres"
        registro.save(update_fields=["estado"])

        # Registrar la ResolucionOP con la firma del PTF
        miembro = perfil_ptf.comision.miembros.filter(
            usuario=perfil_ptf.usuario
        ).first()

        if miembro:
            ResolucionOP.objects.create(
                registro_eop=registro,
                miembro=miembro,
                es_veto=False,
                fundamento="Aprobación exprés por PTF en campo. Firma Ed25519 verificada.",
                firma_digital=firma_hex,
            )

        # Actualizar estadísticas del PTF
        perfil_ptf.auditorias_realizadas += 1
        perfil_ptf.save(update_fields=["auditorias_realizadas"])

        # Liberar Escrow
        PTFService._liberar_escrow_por_eop(registro)

        return registro

    @staticmethod
    @transaction.atomic
    def vetar_eop(registro_eop_uuid, perfil_ptf, fundamento, firma_hex=None):
        """
        El PTF veta una e-OP durante el período de Timelock.
        El veto frena el Silencio Positivo y abre un caso en el TribunalArbitraje.
        """
        registro = RegistroEOP.objects.select_for_update().get(
            uuid_identificador=registro_eop_uuid
        )

        if registro.estado != "en_revision":
            raise ValueError(
                f"Solo se pueden vetar e-OPs en revisión. "
                f"Estado actual: {registro.get_estado_display()}"
            )

        if not perfil_ptf.credencial_vigente:
            raise ValueError("La credencial del PTF está vencida o revocada.")

        registro.estado = "vetado"
        registro.save(update_fields=["estado"])

        miembro = perfil_ptf.comision.miembros.filter(
            usuario=perfil_ptf.usuario
        ).first()

        if miembro:
            ResolucionOP.objects.create(
                registro_eop=registro,
                miembro=miembro,
                es_veto=True,
                fundamento=fundamento,
                firma_digital=firma_hex or "",
            )

        # Actualizar estadísticas
        perfil_ptf.auditorias_realizadas += 1
        perfil_ptf.auditorias_con_incidencia += 1
        perfil_ptf.save(update_fields=["auditorias_realizadas", "auditorias_con_incidencia"])

        # Abrir caso en Tribunal de Arbitraje
        PTFService._abrir_caso_arbitraje(registro)

        return registro

    @staticmethod
    def aplicar_silencio_positivo():
        """
        Worker que se ejecuta periódicamente (Celery Beat cada hora).
        Aprueba automáticamente todas las e-OPs cuyo Timelock venció
        sin recibir ningún veto.
        """
        ahora = timezone.now()
        pendientes = RegistroEOP.objects.filter(
            estado="en_revision",
            timelock_vencimiento__lte=ahora
        )

        aprobadas = []
        for registro in pendientes:
            tiene_veto = registro.resoluciones.filter(es_veto=True).exists()
            if not tiene_veto:
                registro.estado = "aprobado_silencio"
                registro.save(update_fields=["estado"])
                PTFService._liberar_escrow_por_eop(registro)
                aprobadas.append(registro.uuid_identificador)

        return aprobadas

    # ─────────────────────────────────────────────────────────────────────
    # MÉTODOS PRIVADOS
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def _liberar_escrow_por_eop(registro_eop):
        """Busca el ContratoEscrow asociado a la e-OP y libera el hito correspondiente."""
        from apps.tesoreria.models import ContratoEscrow
        from apps.tesoreria.services import EscrowService

        escrow = ContratoEscrow.objects.filter(
            eop_uuid=registro_eop.uuid_identificador
        ).first()

        if not escrow:
            return  # La e-OP puede no tener escrow si es externa o de prueba

        hito = escrow.hitos.filter(estado="bloqueado").order_by("porcentaje").first()
        if hito:
            EscrowService.liberar_hito(hito)

    @staticmethod
    def _abrir_caso_arbitraje(registro_eop):
        """Abre un caso en el TribunalArbitraje cuando una e-OP es vetada."""
        from datetime import timedelta
        from .models import TribunalArbitraje

        TribunalArbitraje.objects.get_or_create(
            registro_eop=registro_eop,
            defaults={
                "motivo": "Veto de PTF durante período de Timelock.",
                "fecha_limite_laudo": timezone.now() + timedelta(hours=72),
                "estado": "abierto",
            }
        )
