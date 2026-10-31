from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.http import FileResponse
from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError

from django.views.generic import ListView, DetailView
from apps.base.models import ConfiguracionEmpresa
from apps.documentos.models import DocumentoAdjunto
from apps.contactos.models import Contacto
from apps.comunicaciones.models import ComunicacionOficial, CedulaDestinatario
from apps.comunicaciones.services import ComunicacionOficialService
from apps.comunicaciones.reports import ComunicacionOficialPDFReport


class ComunicacionListView(ListView):
    """
    Bandeja de entrada / Buzón de Cédulas y Comunicaciones Oficiales en la interfaz web.
    """
    model = ComunicacionOficial
    template_name = "comunicaciones/comunicacion_list.html"
    context_object_name = "comunicaciones"
    ordering = ["-fecha_emision", "-id"]

    def get_queryset(self):
        return ComunicacionOficial.objects.all().prefetch_related("destinatarios")


class ComunicacionDetailView(DetailView):
    """
    Vista de detalle de una Comunicación Oficial / Cédula fehaciente.
    """
    model = ComunicacionOficial
    template_name = "comunicaciones/comunicacion_detail.html"
    context_object_name = "comunicacion"
    slug_field = "uuid_identificador"
    slug_url_kwarg = "uuid"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["destinatarios"] = self.object.destinatarios.select_related("contacto_destino").all()
        return ctx


class ComunicacionesOficialesBuzonAPIView(APIView):
    """
    Buzón oficial de notificaciones fehacientes en el ERP (Domicilio Sectorial Electrónico).
    Filtra cédulas dirigidas a esta empresa o taller y oculta destinatarios CCO a terceros.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        empresa = ConfiguracionEmpresa.objects.first()
        mi_cuit = empresa.cuit if empresa else ""
        cuit_dest = request.headers.get("X-Node-CUIT") or request.GET.get("cuit") or mi_cuit

        if not cuit_dest:
            return Response(
                {"error": "Debe especificar CUIT en header X-Node-CUIT o configurar la empresa local."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        solo_pendientes = request.GET.get("pendientes", "false").lower() == "true"
        qs = CedulaDestinatario.objects.filter(
            cuit_destino=cuit_dest,
            comunicacion__estado="emitida",
        ).select_related("comunicacion", "contacto_destino")

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
                    "contacto": com.contacto_emisor.nombre if com.contacto_emisor else com.cuit_emisor,
                },
                "destinatarios_visibles": visibles,
                "asunto": com.asunto,
                "cuerpo_contenido": com.cuerpo_contenido,
                "estado_notificacion": ced.estado_notificacion,
                "fecha_puesta_disposicion": ced.fecha_puesta_disposicion.isoformat() if ced.fecha_puesta_disposicion else None,
                "fecha_limite_tacita": ced.fecha_limite_tacita.isoformat() if ced.fecha_limite_tacita else None,
                "fecha_notificacion_fehaciente": ced.fecha_notificacion_fehaciente.isoformat() if ced.fecha_notificacion_fehaciente else None,
                "hashes_adjuntos": com.hashes_adjuntos or [],
            })

        return Response({"total": len(data), "cedulas": data}, status=status.HTTP_200_OK)


class ComunicacionOficialEnviarAPIView(APIView):
    """
    Crea, firma y emite una nueva Comunicación Oficial / Cédula desde este ERP.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        empresa = ConfiguracionEmpresa.objects.first()
        mi_cuit = empresa.cuit if empresa else ""
        cuit_emisor = request.data.get("cuit_emisor") or mi_cuit

        if not cuit_emisor:
            return Response({"error": "CUIT del emisor requerido"}, status=status.HTTP_400_BAD_REQUEST)

        tipo = request.data.get("tipo", "nota_oficial")
        alcance = request.data.get("alcance", "individual")
        asunto = request.data.get("asunto")
        cuerpo = request.data.get("cuerpo_contenido")
        es_cifrado = bool(request.data.get("es_cifrado", False))
        destinatarios = request.data.get("destinatarios", [])

        if not asunto or not cuerpo:
            return Response({"error": "Asunto y cuerpo_contenido son obligatorios"}, status=status.HTTP_400_BAD_REQUEST)

        if not destinatarios:
            return Response({"error": "Debe especificar al menos un destinatario en la lista 'destinatarios'"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            borrador = ComunicacionOficialService.crear_borrador(
                cuit_emisor=cuit_emisor,
                tipo=tipo,
                asunto=asunto,
                cuerpo_contenido=cuerpo,
                alcance=alcance,
                destinatarios_iniciales=destinatarios,
                es_cifrado=es_cifrado,
            )

            emitida = ComunicacionOficialService.emitir_comunicacion_oficial(
                borrador.id,
                firma_emisor_hex=request.data.get("firma_hex")
            )

            return Response({
                "status": "emitida",
                "uuid": str(emitida.uuid_identificador),
                "numero_oficial": emitida.numero_oficial,
                "hash_seguridad": emitida.hash_seguridad_payload,
                "fecha_emision": emitida.fecha_emision.isoformat(),
            }, status=status.HTTP_201_CREATED)

        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ComunicacionOficialAcuseAPIView(APIView):
    """
    Estampa acuse de recibo fehaciente (firmado criptográficamente)
    en una cédula dirigida a esta empresa/taller.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, cedula_id):
        firma_acuse_hex = request.data.get("firma_acuse_hex")

        try:
            cedula_actualizada = ComunicacionOficialService.estampar_acuse_recibo(
                cedula_id=cedula_id,
                firma_acuse_hex=firma_acuse_hex,
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
            "emisor": comunicacion.contacto_emisor.nombre if comunicacion.contacto_emisor else comunicacion.cuit_emisor,
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
                comunicacion_id=comunicacion.id,
                archivo_obj=archivo,
                nombre=nombre,
                descripcion=descripcion,
                usuario=request.user if request.user.is_authenticated else None,
            )
            return Response({
                "status": "archivo_adjuntado",
                "adjunto_uuid": item_hash["uuid"],
                "nombre": item_hash["nombre"],
                "sha256": item_hash["sha256"],
                "tamano": item_hash["tamano"],
            }, status=status.HTTP_201_CREATED)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ComunicacionOficialDescargarAdjuntoAPIView(APIView):
    """
    Descarga un archivo adjunto verificando su hash SHA-256.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, uuid, adjunto_uuid):
        comunicacion = ComunicacionOficial.objects.filter(uuid_identificador=uuid).first()
        if not comunicacion:
            return Response({"error": "Comunicación oficial no encontrada"}, status=status.HTTP_404_NOT_FOUND)

        adjunto = DocumentoAdjunto.objects.filter(uuid=adjunto_uuid).first()
        if not adjunto:
            return Response({"error": "Archivo adjunto no encontrado"}, status=status.HTTP_404_NOT_FOUND)

        hash_esperado = None
        for h in (comunicacion.hashes_adjuntos or []):
            if h.get("uuid") == str(adjunto_uuid):
                hash_esperado = h.get("sha256")
                break

        response = FileResponse(adjunto.archivo.open("rb"), content_type=adjunto.mimetype or "application/octet-stream")
        response["Content-Disposition"] = f'attachment; filename="{adjunto.nombre}"'
        if hash_esperado:
            response["X-Digest-SHA256"] = hash_esperado
        return response


class ComunicacionOficialWebhookReceiverAPIView(APIView):
    """
    Endpoint receptor de Webhooks para nodos federados (Push).
    Recibe la cédula enviada desde la MES u otro nodo federado y la registra en la bandeja local.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        data = request.data
        cuit_emisor = data.get("cuit_emisor")
        hash_payload = data.get("hash_seguridad_payload")
        firma_ed25519 = data.get("firma_emisor_ed25519")

        if not cuit_emisor or not hash_payload or not firma_ed25519:
            return Response({"error": "Faltan parámetros criptográficos de la cédula"}, status=status.HTTP_400_BAD_REQUEST)

        # Validación criptográfica con clave pública del contacto (si está registrado)
        contacto_emisor = Contacto.objects.filter(cuil=cuit_emisor).first()
        if contacto_emisor and contacto_emisor.clave_publica_ed25519:
            try:
                vk = VerifyKey(bytes.fromhex(contacto_emisor.clave_publica_ed25519))
                vk.verify(hash_payload.encode(), bytes.fromhex(firma_ed25519))
            except (BadSignatureError, ValueError, TypeError):
                return Response({"error": "Firma Ed25519 del emisor inválida según clave pública registrada"}, status=status.HTTP_403_FORBIDDEN)

        uuid_str = data.get("uuid_identificador")
        comunicacion, _created = ComunicacionOficial.objects.get_or_create(
            uuid_identificador=uuid_str,
            defaults={
                "cuit_emisor": cuit_emisor,
                "contacto_emisor": contacto_emisor,
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
        contacto_destino = Contacto.objects.filter(cuil=cuit_destino).first()

        CedulaDestinatario.objects.get_or_create(
            comunicacion=comunicacion,
            cuit_destino=cuit_destino,
            defaults={
                "contacto_destino": contacto_destino,
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
