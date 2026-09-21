import hashlib
import json
from datetime import timedelta
from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey, SigningKey
from django.conf import settings

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from apps.base.models import ConfiguracionEmpresa
from apps.tesoreria.models import ContratoEscrow
from apps.tesoreria.services import EscrowService

from .models import (
    ComisionCredito,
    PerfilPTF,
    RegistroEOP,
    ResolucionOP,
    TribunalArbitraje,
    VotacionComision,
    VotoComision,
    LineaCreditoFDI,
    Denuncia,
)


class ComisionService:
    """
    Capa de servicios para la Gobernanza Institucional (Votaciones).
    """

    @staticmethod
    def iniciar_votacion(comision_id, objeto_asunto, tipo_asunto):
        """
        Abre una sesión para que la Comisión vote sobre un asunto.
        """
        comision = ComisionCredito.objects.get(pk=comision_id)
        content_type = ContentType.objects.get_for_model(objeto_asunto)

        votacion_abierta = VotacionComision.objects.filter(
            comision=comision,
            content_type=content_type,
            object_id=objeto_asunto.pk,
            tipo_asunto=tipo_asunto,
            estado="abierta",
        ).first()

        if votacion_abierta:
            return votacion_abierta

        return VotacionComision.objects.create(
            comision=comision,
            content_type=content_type,
            object_id=objeto_asunto.pk,
            tipo_asunto=tipo_asunto,
            estado="abierta",
        )

    @staticmethod
    @transaction.atomic
    def emitir_voto(votacion_id, miembro_id, aprueba, fundamento="", firma_hex=None):
        """
        Un miembro de las 7 sillas emite su voto. Si hay mayoría simple (4), ejecuta la acción.
        """
        votacion = VotacionComision.objects.select_for_update().get(pk=votacion_id)

        if votacion.estado != "abierta":
            raise ValueError(f"La votación ya está cerrada ({votacion.estado}).")

        VotoComision.objects.update_or_create(
            votacion=votacion,
            miembro_id=miembro_id,
            defaults={
                "aprueba": aprueba,
                "fundamento": fundamento,
                "firma_digital": firma_hex or "",
            },
        )

        votos = votacion.votos.all()
        positivos = sum(1 for v in votos if v.aprueba)
        negativos = len(votos) - positivos

        if positivos >= 4:
            votacion.estado = "aprobada"
            votacion.fecha_cierre = timezone.now()
            votacion.save(update_fields=["estado", "fecha_cierre"])
            ComisionService._ejecutar_resolucion_aprobada(votacion)
        elif negativos >= 4:
            votacion.estado = "rechazada"
            votacion.fecha_cierre = timezone.now()
            votacion.save(update_fields=["estado", "fecha_cierre"])

        return votacion

    @staticmethod
    def _ejecutar_resolucion_aprobada(votacion):
        if votacion.tipo_asunto == "habilitacion_ptf":
            # El objeto asunto es un User
            PTFService.registrar_ptf(
                usuario=votacion.asunto,
                comision_id=votacion.comision_id,
                municipios_texto=votacion.comision.region,
                rol="ptf_junior",
            )
        elif votacion.tipo_asunto == "aprobacion_credito":
            # El objeto asunto es la LineaCreditoFDI
            linea = votacion.asunto
            # TODO: Notificar al ERP de la marca vía Webhook que se le aprobó crédito
            # requests.post(f"{marca_webhook_url}/api/credito/aprobado", json={"monto": linea.limite_otorgado})
            pass


class PTFService:
    """
    Capa de servicios para el ciclo de vida del Promotor Territorial
    de Formalización (PTF) y su participación en la gobernanza de las e-OPs.

    Responsabilidades:
    - Emisión y verificación de certificados digitales (PKI Federada).
    - Revocación y distribución a nodos externos.
    - Validación de firmas de campo (Ed25519 + GPS + Timelock).
    - Aprobación o veto de e-OPs en el Nodo MES.
    """

    @staticmethod
    @transaction.atomic
    def registrar_ptf(
        usuario, comision_id, municipios_texto, rol="ptf_junior", fecha_vencimiento=None
    ):
        """
        La ComisionCredito registra un nuevo PTF en el sistema.
        El PTF queda en estado inicial sin clave pública — aún no puede firmar.
        La fecha de vencimiento por defecto es 1 año desde hoy.
        """
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
        payload_bytes = payload_str.encode("utf-8")

        # Generar semilla de 32 bytes a partir del SECRET_KEY para emular la clave privada de la MES
        seed = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        signing_key = SigningKey(seed)
        
        # Firmar el payload con Ed25519
        signed = signing_key.sign(payload_bytes)
        firma_mes_hex = signed.signature.hex()

        # Hash para referencia rápida
        hash_certificado = hashlib.sha256(payload_bytes).hexdigest()

        certificado = {
            **payload,
            "hash_certificado": hash_certificado,
            "firma_mes": firma_mes_hex
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

    @staticmethod
    def consultar_ptfs_habilitados():
        """
        Consulta al Nodo MES configurado en el ERP (ej: api.sur.mes.indinopy.ar)
        para traer la lista de PTFs habilitados en esa jurisdicción.
        Esta lista alimenta el combo 'PTF Asignado' en la creación de la e-OP.
        """
        config = ConfiguracionEmpresa.objects.first()

        # Si el ERP está desconectado del FDI o no tiene endpoint, retorna lista local
        # TODO: En Fase 4, hacer requests.get(f"{config.nodo_mes_endpoint}/api/v1/ptfs/habilitados")
        ptfs = PerfilPTF.objects.filter(
            activo=True, fecha_vencimiento_credencial__gte=timezone.now().date()
        )
        return ptfs

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
            True si la firma es válida (matemáticamente verificada con Ed25519), False si no.
        """
        if not perfil_ptf.clave_publica_ed25519:
            raise ValueError("El PTF no tiene clave pública registrada.")

        if not firma_hex or len(firma_hex) != 128:  # 64 bytes Ed25519 = 128 hex chars
            return False

        try:
            # La clave pública se guarda en hex, la pasamos a bytes
            vk = VerifyKey(bytes.fromhex(perfil_ptf.clave_publica_ed25519))

            # El mensaje original (en bytes) es el hash de la OP, firmado
            mensaje_bytes = bytes.fromhex(hash_eop_hex)
            firma_bytes = bytes.fromhex(firma_hex)

            # verify(message, signature)
            vk.verify(mensaje_bytes, firma_bytes)
            return True
        except BadSignatureError:
            return False
        except (ValueError, TypeError):
            # En caso de que haya un error decodificando los hex
            return False

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
        perfil_ptf.save(
            update_fields=["auditorias_realizadas", "auditorias_con_incidencia"]
        )

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
            estado="en_revision", timelock_vencimiento__lte=ahora
        )

        aprobadas = []
        for registro in pendientes:
            tiene_veto = registro.resoluciones.filter(es_veto=True).exists()
            if not tiene_veto:
                # Regla de Negocio: El silencio positivo NO aplica a marcas sin historial.
                tiene_historial = RegistroEOP.objects.filter(
                    comitente_cuit=registro.comitente_cuit,
                    estado__in=["aprobado_silencio", "aprobado_expres"]
                ).exclude(uuid_identificador=registro.uuid_identificador).exists()
                
                if not tiene_historial:
                    continue

                registro.estado = "aprobado_silencio"
                registro.save(update_fields=["estado"])
                PTFService._liberar_escrow_por_eop(registro)
                aprobadas.append(registro.uuid_identificador)

        return aprobadas

    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def _liberar_escrow_por_eop(registro_eop):
        """Busca el ContratoEscrow asociado a la e-OP y libera el hito correspondiente."""
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
        TribunalArbitraje.objects.get_or_create(
            registro_eop=registro_eop,
            defaults={
                "motivo": "Veto de PTF durante período de Timelock.",
                "fecha_limite_laudo": timezone.now() + timedelta(hours=72),
                "estado": "abierto",
            },
        )


class DenunciaService:
    """
    Servicios para el Portal de Denuncias y Reclamos de la Comunidad Organizada.
    Implementa los protocolos tuitivos de inmunidad y cautelares automáticas.
    """

    @staticmethod
    @transaction.atomic
    def radicar_denuncia(
        denunciante, denunciado, motivo, descripcion, evidencia_digital=None
    ):

        denuncia = Denuncia.objects.create(
            denunciante=denunciante,
            denunciado=denunciado,
            motivo=motivo,
            descripcion=descripcion,
            evidencia_digital=evidencia_digital or [],
            estado="ingresada",
        )

        # 1. Inmunidad Fiscal Temporaria (180 días)
        denuncia.inmunidad_fiscal_otorgada = True
        denuncia.fecha_fin_inmunidad = timezone.now().date() + timedelta(days=180)
        denuncia.save(
            update_fields=["inmunidad_fiscal_otorgada", "fecha_fin_inmunidad"]
        )

        # TODO: Webhook a ARCA/AFIP notificando el blindaje del CUIT del tallerista
        # requests.post("https://api.arca.gob.ar/v1/fueros/inmunidad", json={"cuit": denunciante.cuit_o_dni})

        # 2. Si el motivo requiere inmovilización de OPs (Medida Cautelar Automática)
        if motivo in ["precio_bajo_convenio", "retencion_pagos", "amenaza_rescision"]:
            # Solo bloquea e-OPs federadas (FDI). Las OP privadas (producción propia o fasón sin fondeo)
            # viven en el Nodo Marca y no pasan por la MES, por lo que no se inmovilizan.
            ops_activas = RegistroEOP.objects.filter(
                comitente_cuit=denunciado.cuil, 
                estado__in=["en_revision", "aprobado_expres"]
            )
            
            # Guardamos los UUIDs para notificar a la red federada
            uuids_bloqueadas = list(ops_activas.values_list("uuid_identificador", flat=True))
            ops_activas.update(estado="inmovilizada_por_denuncia")
            
            # Sincronizar el estado de bloqueo hacia el Nodo Marca y el Nodo Taller (OP Espejo)
            if uuids_bloqueadas:
                FederacionService.notificar_bloqueo_op_espejo(
                    uuids_bloqueadas, 
                    comitente_cuit=denunciado.cuil, 
                    tallerista_cuit=denunciante.cuil
                )
            
        elif motivo == "coima_funcionario":
            pass
            
        return denuncia


class FederacionService:
    """
    Capa de comunicación (Webhooks) para mantener sincronizados los estados
    entre el Nodo MES Central, los Nodos de las Marcas (Comitentes) y los Nodos de los Talleres.
    """
    @staticmethod
    def _encolar_o_enviar(cuit, tipo_evento, payload):
        """
        Enruta el mensaje según el paradigma de conexión del nodo:
        Si tiene url_base -> PUSH (Webhook asíncrono)
        Si no tiene -> PULL (Encola en NovedadFederada para Polling)
        """
        from apps.federacion.models import NodoFederado, NovedadFederada
        try:
            nodo = NodoFederado.objects.get(cuit=cuit)
        except NodoFederado.DoesNotExist:
            return # Nodo no registrado, no hay a quien notificar

        if nodo.url_base:
            # Tiene IP pública / Túnel (Paradigma PUSH)
            # Acá encolaríamos una tarea de Celery (requests.post a nodo.url_base)
            pass 
        else:
            # Paradigma On-Premise clásico (Paradigma PULL / Polling)
            NovedadFederada.objects.create(
                nodo_destino=nodo,
                tipo_evento=tipo_evento,
                payload=payload
            )

    @staticmethod
    def notificar_bloqueo_op_espejo(uuids_bloqueadas, comitente_cuit, tallerista_cuit):
        """
        Notifica a los ERPs periféricos que ciertas e-OPs fueron inmovilizadas.
        Esto gatilla el bloqueo del stock y pagos en la OP Espejo del taller.
        """
        payload = {
            "estado": "inmovilizada_por_denuncia",
            "motivo": "Cautelar Comunidad Organizada",
            "uuids": [str(u) for u in uuids_bloqueadas]
        }
        
        FederacionService._encolar_o_enviar(comitente_cuit, "bloqueo_eop", payload)
        FederacionService._encolar_o_enviar(tallerista_cuit, "bloqueo_eop", payload)

    @staticmethod
    def notificar_resolucion_aprobada(tipo_asunto, objeto_serializado, cuit_destino):
        """
        Comunica una decisión de la Comisión al nodo correspondiente.
        """
        FederacionService._encolar_o_enviar(cuit_destino, f"resolucion_{tipo_asunto}", objeto_serializado)
