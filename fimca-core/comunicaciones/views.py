from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.http import FileResponse
from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError

from federacion.models import NodoFederado, WebhookLog
from base.models import ConfiguracionEmpresa, DocumentoAdjunto
from comunicaciones.models import ComunicacionOficial, CedulaDestinatario
from comunicaciones.services import ComunicacionOficialService
from comunicaciones.reports import ComunicacionOficialPDFReport


class ComunicacionesOficialesBuzonAPIView(APIView):
    """
    Buzón oficial de notificaciones fehacientes (Domicilio Fiscal/Sectorial Electrónico).
    Filtra cédulas dirigidas al nodo autenticado y oculta los destinatarios CCO a terceros.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        cuit_dest = request.headers.get("X-Node-CUIT") or request.GET.get("cuit")
        if not cuit_dest:
            return Response(
                {"error": "Debe especificar CUIT en header X-Node-CUIT o query param ?cuit="},
                status=status.HTTP_400_BAD_REQUEST,
            )

        solo_pendientes = request.GET.get("pendientes", "false").lower() == "true"
        qs = CedulaDestinatario.objects.filter(
            cuit_destino=cuit_dest,
            comunicacion__estado="emitida",
        ).select_related("comunicacion", "comunicacion__nodo_emisor")

        if solo_pendientes:
            qs = qs.filter(estado_notificacion__in=["pendiente", "entregada"])

        data = []
        for ced in qs:
            com = ced.comunicacion
            visibles = list(
                com.destinatarios.filter(modo_recepcion__in=["principal", "copia_publica"]).values(
                    "cuit_destino", "modo_recepcion"
                )
            )

            data.append({
                "cedula_id": ced.id,
                "comunicacion_uuid": str(com.uuid_identificador),
                "numero_oficial": com.numero_oficial,
                "tipo": com.tipo,
                "alcance": com.alcance,
                "modo_recepcion": ced.modo_recepcion,
                "emisor": {
                    "cuit": com.cuit_emisor,
                    "nodo": com.nodo_emisor.nombre,
                },
                "destinatarios_visibles": visibles,
                "asunto": com.asunto,
                "cuerpo_contenido": com.cuerpo_contenido,
                "es_cifrado": com.es_cifrado,
                "hash_payload": com.hash_seguridad_payload,
                "hashes_adjuntos": com.hashes_adjuntos,
                "firma_emisor": com.firma_emisor_ed25519,
                "estado_notificacion": ced.estado_notificacion,
                "fecha_emision": com.fecha_emision.isoformat() if com.fecha_emision else None,
                "fecha_puesta_disposicion": ced.fecha_puesta_disposicion.isoformat() if ced.fecha_puesta_disposicion else None,
                "fecha_limite_tacita": ced.fecha_limite_tacita.isoformat() if ced.fecha_limite_tacita else None,
                "fecha_notificacion_fehaciente": ced.fecha_notificacion_fehaciente.isoformat() if ced.fecha_notificacion_fehaciente else None,
            })

        return Response(data, status=status.HTTP_200_OK)


class ComunicacionOficialEnviarAPIView(APIView):
    """
    Crea un borrador o emite una Comunicación Oficial / Cédula Pluripersonal en la red federada.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        cuit_emisor = request.data.get("cuit_emisor")
        tipo = request.data.get("tipo", "nota_oficial")
        alcance = request.data.get("alcance", "individual")
        asunto = request.data.get("asunto")
        cuerpo = request.data.get("cuerpo")
        es_cifrado = request.data.get("es_cifrado", False)
        adjuntos = request.data.get("hashes_adjuntos", [])
        destinatarios_raw = request.data.get("destinatarios", [])
        emitir_ahora = request.data.get("emitir_ahora", True)
        firma_emisor = request.data.get("firma_emisor_ed25519")

        if not all([cuit_emisor, asunto, cuerpo]):
            return Response(
                {"error": "Faltan parámetros obligatorios (cuit_emisor, asunto, cuerpo)"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        nodo_emisor = NodoFederado.objects.filter(cuit=cuit_emisor).first()
        if not nodo_emisor:
            return Response(
                {"error": "Nodo emisor no registrado en el directorio federado"},
                status=status.HTTP_404_NOT_FOUND,
            )

        destinatarios_preparados = []
        for d in destinatarios_raw:
            cuit_d = d.get("cuit")
            nodo_d = NodoFederado.objects.filter(cuit=cuit_d).first()
            if nodo_d:
                destinatarios_preparados.append({
                    "nodo_destino": nodo_d,
                    "cuit_destino": cuit_d,
                    "modo": d.get("modo", "principal"),
                })

        borrador = ComunicacionOficialService.crear_borrador(
            nodo_emisor=nodo_emisor,
            cuit_emisor=cuit_emisor,
            tipo=tipo,
            alcance=alcance,
            asunto=asunto,
            cuerpo_contenido=cuerpo,
            destinatarios_iniciales=destinatarios_preparados,
            es_cifrado=es_cifrado,
            hashes_adjuntos=adjuntos,
        )

        if not emitir_ahora:
            return Response({
                "status": "borrador_creado",
                "uuid": str(borrador.uuid_identificador),
                "estado": borrador.estado,
            }, status=status.HTTP_201_CREATED)

        try:
            comunicacion = ComunicacionOficialService.emitir_comunicacion_oficial(
                comunicacion_id=borrador.id,
                firma_emisor_hex=firma_emisor,
            )
            return Response({
                "status": "comunicacion_emitida",
                "uuid": str(comunicacion.uuid_identificador),
                "numero_oficial": comunicacion.numero_oficial,
                "hash_payload": comunicacion.hash_seguridad_payload,
                "total_destinatarios": comunicacion.destinatarios.count(),
                "fecha_emision": comunicacion.fecha_emision.isoformat(),
            }, status=status.HTTP_201_CREATED)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ComunicacionOficialAcuseAPIView(APIView):
    """
    Registra el acuse de recibo fehaciente de una cédula por su ID o UUID.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, cedula_id):
        firma_acuse = request.data.get("firma_acuse_recibo")
        if not firma_acuse:
            return Response({"error": "Se requiere firma_acuse_recibo Ed25519"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            cedula_actualizada = ComunicacionOficialService.registrar_acuse_recibo(
                cedula_id=cedula_id,
                firma_acuse_hex=firma_acuse,
            )
            return Response({
                "status": "acuse_registrado",
                "numero_oficial": cedula_actualizada.comunicacion.numero_oficial,
                "cuit_destino": cedula_actualizada.cuit_destino,
                "estado": cedula_actualizada.estado_notificacion,
                "fecha_fehaciente": cedula_actualizada.fecha_notificacion_fehaciente.isoformat(),
            }, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)


class ComunicacionOficialDetalleDescargaAPIView(APIView):
    """
    Consulta de detalle y descarga en PDF oficial de una Comunicación / Cédula.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, uuid):
        comunicacion = ComunicacionOficial.objects.filter(uuid_identificador=uuid).first()
        if not comunicacion:
            return Response({"error": "Comunicación oficial no encontrada"}, status=status.HTTP_404_NOT_FOUND)

        cuit_observador = request.headers.get("X-Node-CUIT") or request.GET.get("cuit")

        if request.GET.get("format") == "pdf":
            reporte = ComunicacionOficialPDFReport(
                comunicacion=comunicacion,
                cuit_observador=cuit_observador,
            )
            return reporte.to_http_response(inline=True)

        es_emisor = (cuit_observador == comunicacion.cuit_emisor) or (cuit_observador is None)
        destinatarios_qs = comunicacion.destinatarios.all()
        if not es_emisor:
            destinatarios_qs = destinatarios_qs.filter(
                modo_recepcion__in=["principal", "copia_publica"]
            ) | destinatarios_qs.filter(cuit_destino=cuit_observador)

        dests = list(destinatarios_qs.values(
            "id", "cuit_destino", "modo_recepcion", "estado_notificacion",
            "fecha_notificacion_fehaciente", "fecha_limite_tacita"
        ))

        return Response({
            "uuid": str(comunicacion.uuid_identificador),
            "numero_oficial": comunicacion.numero_oficial,
            "tipo": comunicacion.tipo,
            "alcance": comunicacion.alcance,
            "estado": comunicacion.estado,
            "cuit_emisor": comunicacion.cuit_emisor,
            "nodo_emisor": comunicacion.nodo_emisor.nombre,
            "asunto": comunicacion.asunto,
            "cuerpo_contenido": comunicacion.cuerpo_contenido,
            "hash_payload": comunicacion.hash_seguridad_payload,
            "hashes_adjuntos": comunicacion.hashes_adjuntos or [],
            "firma_emisor": comunicacion.firma_emisor_ed25519,
            "fecha_emision": comunicacion.fecha_emision.isoformat() if comunicacion.fecha_emision else None,
            "destinatarios": dests,
        }, status=status.HTTP_200_OK)


class ComunicacionOficialAdjuntarAPIView(APIView):
    """
    Sube un archivo adjunto a una comunicación oficial en estado BORRADOR.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, uuid):
        comunicacion = ComunicacionOficial.objects.filter(uuid_identificador=uuid).first()
        if not comunicacion:
            return Response({"error": "Comunicación oficial no encontrada"}, status=status.HTTP_404_NOT_FOUND)

        archivo = request.FILES.get("archivo")
        if not archivo:
            return Response({"error": "Debe enviar un archivo en el campo 'archivo'"}, status=status.HTTP_400_BAD_REQUEST)

        descripcion = request.data.get("descripcion", "")
        nombre = request.data.get("nombre") or archivo.name

        try:
            adjunto, item_hash = ComunicacionOficialService.adjuntar_archivo(
                comunicacion_id=comunicacion.pk,
                archivo_obj=archivo,
                nombre=nombre,
                descripcion=descripcion,
                usuario=request.user if request.user and request.user.is_authenticated else None,
            )
            return Response({
                "status": "archivo_adjuntado",
                "adjunto_uuid": str(adjunto.uuid),
                "item_hash": item_hash,
                "total_adjuntos": len(comunicacion.hashes_adjuntos),
            }, status=status.HTTP_201_CREATED)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ComunicacionOficialDescargarAdjuntoAPIView(APIView):
    """
    Descarga un archivo adjunto con cabecera de verificación SHA-256.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, uuid, adjunto_uuid):
        comunicacion = ComunicacionOficial.objects.filter(uuid_identificador=uuid).first()
        if not comunicacion:
            return Response({"error": "Comunicación oficial no encontrada"}, status=status.HTTP_404_NOT_FOUND)

        adjunto = comunicacion.adjuntos.filter(uuid=adjunto_uuid).first()
        if not adjunto or not adjunto.archivo:
            return Response({"error": "Archivo adjunto no encontrado en esta comunicación"}, status=status.HTTP_404_NOT_FOUND)

        hash_esperado = ""
        for h in (comunicacion.hashes_adjuntos or []):
            if h.get("uuid") == str(adjunto.uuid):
                hash_esperado = h.get("sha256", "")
                break

        response = FileResponse(adjunto.archivo.open("rb"), content_type=adjunto.mimetype or "application/octet-stream")
        response["Content-Disposition"] = f'attachment; filename="{adjunto.nombre}"'
        if hash_esperado:
            response["X-Digest-SHA256"] = hash_esperado
        return response


class ComunicacionOficialWebhookReceiverAPIView(APIView):
    """
    Endpoint receptor de Webhooks para nodos federados (Push).
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        data = request.data
        cuit_emisor = data.get("cuit_emisor")
        hash_payload = data.get("hash_seguridad_payload")
        firma_ed25519 = data.get("firma_emisor_ed25519")

        nodo_emisor = NodoFederado.objects.filter(cuit=cuit_emisor).first()
        log = WebhookLog.objects.create(
            nodo_origen=nodo_emisor,
            endpoint=request.path,
            metodo="POST",
            payload_recibido=data,
            ip_origen=request.META.get("REMOTE_ADDR"),
            firma_verificada=False,
            status_code_devuelto=200,
        )

        if not cuit_emisor or not hash_payload or not firma_ed25519:
            log.status_code_devuelto = 400
            log.save(update_fields=["status_code_devuelto"])
            return Response({"error": "Faltan parámetros criptográficos de la cédula"}, status=status.HTTP_400_BAD_REQUEST)

        if nodo_emisor and nodo_emisor.clave_publica_nodo:
            try:
                vk = VerifyKey(bytes.fromhex(nodo_emisor.clave_publica_nodo))
                vk.verify(hash_payload.encode(), bytes.fromhex(firma_ed25519))
                log.firma_verificada = True
                log.save(update_fields=["firma_verificada"])
            except (BadSignatureError, ValueError, TypeError):
                log.status_code_devuelto = 403
                log.save(update_fields=["status_code_devuelto"])
                return Response({"error": "Firma Ed25519 del emisor inválida"}, status=status.HTTP_403_FORBIDDEN)

        uuid_str = data.get("uuid_identificador")
        comunicacion, _created = ComunicacionOficial.objects.get_or_create(
            uuid_identificador=uuid_str,
            defaults={
                "nodo_emisor": nodo_emisor,
                "cuit_emisor": cuit_emisor,
                "numero_oficial": data.get("numero_oficial"),
                "tipo": data.get("tipo", "nota_oficial"),
                "asunto": data.get("asunto", ""),
                "cuerpo_contenido": data.get("cuerpo_contenido", ""),
                "es_cifrado": data.get("es_cifrado", False),
                "hash_seguridad_payload": hash_payload,
                "hashes_adjuntos": data.get("hashes_adjuntos", []),
                "firma_emisor_ed25519": firma_ed25519,
                "estado": "emitida",
                "fecha_emision": data.get("fecha_emision") or timezone.now(),
            }
        )

        cuit_destino = data.get("cuit_destino")
        nodo_destino = NodoFederado.objects.filter(cuit=cuit_destino).first() or nodo_emisor

        CedulaDestinatario.objects.get_or_create(
            comunicacion=comunicacion,
            cuit_destino=cuit_destino,
            defaults={
                "nodo_destino": nodo_destino,
                "modo_recepcion": data.get("modo_recepcion", "principal"),
                "estado_notificacion": "entregada",
                "fecha_puesta_disposicion": timezone.now(),
                "fecha_limite_tacita": data.get("fecha_limite_tacita"),
            }
        )

        return Response({
            "status": "recibida_en_buzon",
            "numero_oficial": comunicacion.numero_oficial,
            "uuid": str(comunicacion.uuid_identificador),
        }, status=status.HTTP_201_CREATED)
