import json
import hashlib
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from django.conf import settings
from nacl.signing import SigningKey, VerifyKey
from nacl.exceptions import BadSignatureError
from apps.base.services import SecuenciaService


class ComunicacionOficialService:
    """
    Motor de Comunicaciones Oficiales y Cédulas Electrónicas Inter-Nodo (Store-and-Forward Criptográfico).
    Implementación para Nodo ERP (Marcas y Talleres):
    1. Borradores internos editables.
    2. Cédulas Pluripersonales (Destinatarios Principales TO, Copia Abierta CC y Copia Oculta CCO).
    3. Firma Ed25519 inmutable al emitir y sellado de número oficial.
    4. Acuse individual fehaciente por destinatario con cómputo de 48h (notificación tácita de oficio).
    5. Asociación flexible a la libreta local de Contactos por CUIT.
    """

    @staticmethod
    def _calcular_hash_comunicacion(datos_dict):
        canonica = json.dumps(datos_dict, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(canonica).hexdigest()

    @staticmethod
    def crear_borrador(
        cuit_emisor,
        tipo,
        asunto,
        cuerpo_contenido,
        alcance="individual",
        destinatarios_iniciales=None,
        es_cifrado=False,
        hashes_adjuntos=None,
    ):
        from apps.comunicaciones.models import ComunicacionOficial, CedulaDestinatario
        from apps.contactos.models import Contacto

        contacto_emisor = Contacto.objects.filter(cuil=cuit_emisor).first()

        comunicacion = ComunicacionOficial.objects.create(
            cuit_emisor=cuit_emisor,
            contacto_emisor=contacto_emisor,
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
                cuit_d = d["cuit_destino"]
                cont_dest = Contacto.objects.filter(cuil=cuit_d).first()
                CedulaDestinatario.objects.create(
                    comunicacion=comunicacion,
                    cuit_destino=cuit_d,
                    contacto_destino=cont_dest,
                    modo_recepcion=d.get("modo", "principal"),
                    estado_notificacion="pendiente",
                )

        return comunicacion

    @staticmethod
    def adjuntar_archivo(comunicacion_id, archivo_obj, nombre=None, descripcion="", usuario=None):
        from django.contrib.contenttypes.models import ContentType
        from apps.comunicaciones.models import ComunicacionOficial
        from apps.documentos.models import DocumentoAdjunto

        comunicacion = ComunicacionOficial.objects.get(pk=comunicacion_id)
        if comunicacion.estado != "borrador":
            raise ValueError("No se pueden adjuntar archivos a una comunicación oficial ya emitida o archivada.")

        sha256 = hashlib.sha256()
        for chunk in archivo_obj.chunks():
            sha256.update(chunk)
        digest_hex = sha256.hexdigest()

        if hasattr(archivo_obj, "seek"):
            archivo_obj.seek(0)

        nombre_archivo = nombre or getattr(archivo_obj, "name", "adjunto_desconocido")
        ct = ContentType.objects.get_for_model(ComunicacionOficial)

        adjunto = DocumentoAdjunto.objects.create(
            content_type=ct,
            object_id=comunicacion.pk,
            nombre=nombre_archivo,
            archivo=archivo_obj,
            descripcion=descripcion,
            subido_por=usuario,
            res_model="comunicaciones.comunicacionoficial",
            res_id=comunicacion.pk,
        )

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
        from apps.comunicaciones.models import ComunicacionOficial

        comunicacion = ComunicacionOficial.objects.select_for_update().get(pk=comunicacion_id)
        if comunicacion.estado != "borrador":
            raise ValueError("Solo se pueden emitir comunicaciones en estado borrador.")

        destinatarios = list(comunicacion.destinatarios.all())
        if not destinatarios:
            raise ValueError("La comunicación debe tener al menos un destinatario asignado.")

        numero = SecuenciaService.obtener_siguiente_numero(
            ComunicacionOficial.SECUENCIA_CODIGO,
            fecha=timezone.now().date(),
        )

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

        comunicacion.destinatarios.all().update(
            estado_notificacion="entregada",
            fecha_puesta_disposicion=ahora,
            fecha_limite_tacita=limite_tacito,
        )

        # Despacho asíncrono a la Red / MES / Webhook
        try:
            from apps.comunicaciones.tasks import despachar_cedula_webhook_async
            cedula_ids = list(comunicacion.destinatarios.values_list("id", flat=True))
            for cid in cedula_ids:
                transaction.on_commit(lambda _id=cid: despachar_cedula_webhook_async.delay(_id))
        except ImportError:
            pass

        return comunicacion

    @staticmethod
    def estampar_acuse_recibo(cedula_id, signing_key_destinatario=None, firma_acuse_hex=None):
        from apps.comunicaciones.models import CedulaDestinatario

        cedula = CedulaDestinatario.objects.select_related("comunicacion").get(pk=cedula_id)

        if cedula.estado_notificacion in ["notificada_expresa", "notificada_tacita"]:
            return cedula

        datos_acuse = {
            "cedula_id": cedula.id,
            "numero_oficial": cedula.comunicacion.numero_oficial,
            "cuit_destino": cedula.cuit_destino,
            "timestamp": timezone.now().isoformat(),
        }
        hash_acuse = ComunicacionOficialService._calcular_hash_comunicacion(datos_acuse)

        if not firma_acuse_hex:
            if not signing_key_destinatario:
                seed = hashlib.sha256(f"ACUSE_{cedula.cuit_destino}_{settings.SECRET_KEY}".encode()).digest()
                signing_key_destinatario = SigningKey(seed)
            firma_acuse_hex = signing_key_destinatario.sign(hash_acuse.encode()).signature.hex()

        ahora = timezone.now()
        cedula.firma_acuse_recibo = firma_acuse_hex
        cedula.fecha_notificacion_fehaciente = ahora
        cedula.estado_notificacion = "notificada_expresa"
        cedula.save(update_fields=[
            "firma_acuse_recibo", "fecha_notificacion_fehaciente", "estado_notificacion"
        ])

        return cedula

    @staticmethod
    def procesar_notificaciones_tacitas():
        from apps.comunicaciones.models import CedulaDestinatario

        ahora = timezone.now()
        vencidas = CedulaDestinatario.objects.filter(
            estado_notificacion="entregada",
            fecha_limite_tacita__lte=ahora,
        )
        total = vencidas.count()
        vencidas.update(
            estado_notificacion="notificada_tacita",
            fecha_notificacion_fehaciente=ahora,
        )
        return total
