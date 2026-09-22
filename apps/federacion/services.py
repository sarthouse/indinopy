import requests
from django.db import transaction
from django.conf import settings
from apps.base.models import ConfiguracionEmpresa

class FederacionCreditoService:
    """
    Servicio cliente para consumir las APIs del Nodo Central (MES).
    """
    
    @staticmethod
    def consultar_cupo_mes():
        """
        Consulta en tiempo real (Pull) el estado del crédito y la mora
        al servidor de la MES.
        """
        empresa = ConfiguracionEmpresa.objects.first()
        if not empresa:
            raise ValueError("No hay una ConfiguracionEmpresa definida en este nodo.")
        
        mi_cuit = empresa.cuit
        
        # En producción, esta URL vendría de settings. NODO_MES_URL
        mes_url = getattr(settings, 'NODO_MES_URL', 'http://localhost:8000')
        endpoint = f"{mes_url}/mes/api/v1/fdi/estado-credito/"
        
        try:
            # Petición HTTP al nodo MES. Se inyecta el CUIT propio en los headers
            respuesta = requests.get(
                endpoint,
                headers={"X-CUIT": mi_cuit},
                timeout=5
            )
            
            if respuesta.status_code == 200:
                return respuesta.json()
            elif respuesta.status_code == 404:
                raise ValueError("La MES informa que tu empresa no tiene una línea de crédito asignada.")
            else:
                raise ValueError(f"Error de red comunicándose con la MES: {respuesta.status_code}")
                
        except requests.RequestException as e:
            raise ValueError(f"El Nodo MES no está disponible: {str(e)}")

    @staticmethod
    def transmitir_eop_a_mes(contrato_eop, firma_comitente_hex, clave_publica_hex):
        """
        Emite el HTTP POST con el payload canónico firmado hacia el endpoint de la MES
        (/federacion/eop/entrante/).
        """
        import json
        from decimal import Decimal

        empresa = ConfiguracionEmpresa.objects.first()
        if not empresa:
            raise ValueError("No hay una ConfiguracionEmpresa definida en este nodo.")

        mes_url = getattr(settings, 'NODO_MES_URL', 'http://localhost:8000').rstrip('/')
        endpoint = f"{mes_url}/federacion/eop/entrante/"

        # Aseguramos el hash de seguridad
        contrato_eop.sellar_hash_seguridad()

        payload_canonico_str = contrato_eop.generar_payload_canonico()
        payload_canonico_dict = json.loads(payload_canonico_str)

        sobre_transporte = {
            "uuid_identificador": str(contrato_eop.uuid_identificador),
            "hash_seguridad": contrato_eop.hash_seguridad,
            "comitente_cuit": empresa.cuit,
            "tallerista_cuit": payload_canonico_dict.get("tallerista_cuit", ""),
            "monto_total_uci": str(contrato_eop.monto_total_uci),
            "payload_canonico": payload_canonico_dict,
            "firma_comitente": firma_comitente_hex,
            "clave_publica_comitente": clave_publica_hex,
            "cronograma_escrow_hitos": payload_canonico_dict.get("cronograma_escrow_hitos", []),
        }

        try:
            respuesta = requests.post(
                endpoint,
                json=sobre_transporte,
                headers={"X-CUIT": empresa.cuit, "Content-Type": "application/json"},
                timeout=10,
            )
            if respuesta.status_code in [200, 201]:
                return respuesta.json()
            else:
                raise ValueError(
                    f"Error rechazado por la MES ({respuesta.status_code}): {respuesta.text}"
                )
        except requests.RequestException as e:
            raise ValueError(f"Fallo de conexión al despachar e-OP al Nodo MES: {str(e)}")


class ComunicacionOficialService:
    """
    Motor de Comunicaciones Oficiales y Cédulas Electrónicas Inter-Nodo (Store-and-Forward Criptográfico).
    Soporta:
    1. Borradores internos editables.
    2. Cédulas Pluripersonales (Destinatarios Principales TO, Copia Abierta CC y Copia Oculta CCO).
    3. Firma Ed25519 inmutable al emitir y sellado de número oficial.
    4. Acuse individual fehaciente por destinatario con cómputo de 48h (notificación tácita de oficio).
    """

    @staticmethod
    def _calcular_hash_comunicacion(datos_dict):
        import json
        import hashlib
        canonica = json.dumps(datos_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(canonica).hexdigest()

    @staticmethod
    def crear_borrador(
        nodo_emisor,
        cuit_emisor,
        tipo,
        asunto,
        cuerpo_contenido,
        alcance="individual",
        destinatarios_iniciales=None,
        es_cifrado=False,
        hashes_adjuntos=None,
    ):
        """
        Crea una comunicación oficial en estado BORRADOR (no tiene número oficial ni firma).
        destinatarios_iniciales: lista de dicts [{'nodo_destino_id': X, 'cuit_destino': '...', 'modo': 'principal'|'copia_publica'|'copia_oculta'}]
        """
        from apps.federacion.models import ComunicacionOficialFederada, CedulaDestinatario, NodoFederado

        comunicacion = ComunicacionOficialFederada.objects.create(
            nodo_emisor=nodo_emisor,
            cuit_emisor=cuit_emisor,
            tipo=tipo,
            alcance=alcance,
            asunto=asunto,
            cuerpo_contenido=cuerpo_contenido,
            es_cifrado=es_cifrado,
            hashes_adjuntos=hashes_adjuntos or [],
            estado="borrador",
        )

        if destinatarios_iniciales:
            for d in destinatarios_iniciales:
                nodo_dest = d.get("nodo_destino") or NodoFederado.objects.get(pk=d["nodo_destino_id"])
                CedulaDestinatario.objects.create(
                    comunicacion=comunicacion,
                    nodo_destino=nodo_dest,
                    cuit_destino=d["cuit_destino"],
                    modo_recepcion=d.get("modo", "principal"),
                    estado_notificacion="pendiente",
                )

        return comunicacion

    @staticmethod
    def adjuntar_archivo(comunicacion_id, archivo_obj, nombre=None, descripcion="", usuario=None):
        """
        Adjunta un archivo físico a una comunicación oficial en estado borrador.
        Calcula el hash SHA-256 del contenido binario y actualiza la lista hashes_adjuntos.
        """
        import hashlib
        from django.contrib.contenttypes.models import ContentType
        from apps.federacion.models import ComunicacionOficialFederada
        from apps.documentos.models import DocumentoAdjunto

        comunicacion = ComunicacionOficialFederada.objects.get(pk=comunicacion_id)
        if comunicacion.estado != "borrador":
            raise ValueError("No se pueden adjuntar archivos a una comunicación oficial ya emitida o archivada.")

        # Calcular SHA-256 en chunks
        sha256 = hashlib.sha256()
        for chunk in archivo_obj.chunks():
            sha256.update(chunk)
        digest_hex = sha256.hexdigest()

        # Resetear puntero de lectura para que Django pueda guardarlo
        if hasattr(archivo_obj, "seek"):
            archivo_obj.seek(0)

        nombre_archivo = nombre or getattr(archivo_obj, "name", "adjunto_desconocido")
        ct = ContentType.objects.get_for_model(ComunicacionOficialFederada)

        adjunto = DocumentoAdjunto.objects.create(
            content_type=ct,
            object_id=comunicacion.pk,
            nombre=nombre_archivo,
            archivo=archivo_obj,
            descripcion=descripcion,
            subido_por=usuario,
        )

        # Actualizar hashes_adjuntos en la comunicación
        item_hash = {
            "uuid": str(adjunto.uuid),
            "nombre": adjunto.nombre,
            "mimetype": adjunto.mimetype,
            "tamano": adjunto.tamano,
            "sha256": digest_hex,
        }

        hashes = list(comunicacion.hashes_adjuntos or [])
        hashes.append(item_hash)
        comunicacion.hashes_adjuntos = hashes
        comunicacion.save(update_fields=["hashes_adjuntos"])

        return adjunto, item_hash

    @staticmethod
    @transaction.atomic
    def emitir_comunicacion_oficial(comunicacion_id, signing_key_emisor=None, firma_emisor_hex=None):
        """
        Firma y emite la comunicación oficial.
        Asigna el número oficial anual correlativo, sella el hash SHA-256 público
        y activa el reloj perentorio de 48 horas en cada cédula de notificación.
        """
        from django.utils import timezone
        from datetime import timedelta
        from nacl.signing import SigningKey
        import hashlib
        from apps.base.services import SecuenciaService
        from apps.federacion.models import ComunicacionOficialFederada, CedulaDestinatario

        comunicacion = ComunicacionOficialFederada.objects.select_for_update().get(pk=comunicacion_id)
        if comunicacion.estado != "borrador":
            raise ValueError("Solo se pueden emitir comunicaciones en estado borrador.")

        destinatarios = list(comunicacion.destinatarios.all())
        if not destinatarios:
            raise ValueError("La comunicación debe tener al menos un destinatario asignado.")

        # Asignar número correlativo oficial
        numero = SecuenciaService.obtener_siguiente_numero(
            ComunicacionOficialFederada.SECUENCIA_CODIGO,
            fecha=timezone.now().date(),
        )

        # Destinatarios públicos (TO y CC) para el hash canónico visible
        publicos = [
            {"cuit": d.cuit_destino, "modo": d.modo_recepcion}
            for d in destinatarios
            if d.modo_recepcion in ["principal", "copia_publica"]
        ]

        datos_canonicos = {
            "numero_oficial": numero,
            "cuit_emisor": comunicacion.cuit_emisor,
            "destinatarios_visibles": publicos,
            "tipo": comunicacion.tipo,
            "asunto": comunicacion.asunto,
            "cuerpo_contenido": comunicacion.cuerpo_contenido,
            "es_cifrado": comunicacion.es_cifrado,
            "hashes_adjuntos": comunicacion.hashes_adjuntos or [],
            "fecha_emision": timezone.now().isoformat(),
        }

        hash_payload = ComunicacionOficialService._calcular_hash_comunicacion(datos_canonicos)

        if not firma_emisor_hex:
            if not signing_key_emisor:
                seed = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
                signing_key_emisor = SigningKey(seed)
            firma_emisor_hex = signing_key_emisor.sign(hash_payload.encode()).signature.hex()

        ahora = timezone.now()
        limite_tacito = ahora + timedelta(hours=48)

        comunicacion.numero_oficial = numero
        comunicacion.hash_seguridad_payload = hash_payload
        comunicacion.firma_emisor_ed25519 = firma_emisor_hex
        comunicacion.estado = "emitida"
        comunicacion.fecha_emision = ahora
        comunicacion.save(update_fields=[
            "numero_oficial", "hash_seguridad_payload", "firma_emisor_ed25519", "estado", "fecha_emision"
        ])

        # Activar el cómputo de notificación en cada cédula de destinatario
        comunicacion.destinatarios.all().update(
            estado_notificacion="entregada",
            fecha_puesta_disposicion=ahora,
            fecha_limite_tacita=limite_tacito,
        )

        # Encolar el despacho asincrónico por Celery hacia cada nodo destino
        from apps.federacion.tasks import despachar_cedula_webhook_async
        cedula_ids = list(comunicacion.destinatarios.values_list("id", flat=True))
        for cid in cedula_ids:
            transaction.on_commit(lambda _id=cid: despachar_cedula_webhook_async.delay(_id))

        return comunicacion

    @staticmethod
    def registrar_acuse_recibo(cedula_id, firma_acuse_hex):
        """
        Registra el acuse de recibo fehaciente emitido por un destinatario específico (TO/CC/CCO).
        Valida la firma Ed25519 contra la clave pública del nodo destinatario.
        """
        from django.utils import timezone
        from nacl.signing import VerifyKey
        from nacl.exceptions import BadSignatureError
        from apps.federacion.models import CedulaDestinatario

        cedula = CedulaDestinatario.objects.select_related("comunicacion", "nodo_destino").get(pk=cedula_id)

        clave_pub = cedula.nodo_destino.clave_publica_nodo
        if clave_pub:
            try:
                vk = VerifyKey(bytes.fromhex(clave_pub))
                vk.verify(cedula.comunicacion.hash_seguridad_payload.encode(), bytes.fromhex(firma_acuse_hex))
            except (BadSignatureError, ValueError, TypeError):
                cedula.estado_notificacion = "rechazada"
                cedula.save(update_fields=["estado_notificacion"])
                raise ValueError("La firma del acuse de recibo no coincide con la clave pública del nodo destinatario.")

        cedula.firma_acuse_recibo = firma_acuse_hex
        cedula.estado_notificacion = "notificada_expresa"
        cedula.fecha_notificacion_fehaciente = timezone.now()
        cedula.save(update_fields=["firma_acuse_recibo", "estado_notificacion", "fecha_notificacion_fehaciente"])
        return cedula

    @staticmethod
    def procesar_notificaciones_tacitas():
        """
        Worker periódico (Celery Beat):
        Aplica la notificación tácita por transcurso de 48 horas de puesta a disposición en el Domicilio Electrónico.
        """
        from django.utils import timezone
        from apps.federacion.models import CedulaDestinatario

        vencidas = CedulaDestinatario.objects.filter(
            estado_notificacion__in=["pendiente", "entregada"],
            fecha_limite_tacita__lte=timezone.now(),
        )
        total = vencidas.update(
            estado_notificacion="notificada_tacita",
            fecha_notificacion_fehaciente=timezone.now(),
        )
        return total


