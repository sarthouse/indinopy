import datetime
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from .models import NodoFederado, WebhookLog
from .serializers import (
    NodoFederadoSerializer, 
    EntradaEOPSerializer, 
    FirmaEtapaSerializer
)
from apps.mes.models import RegistroEOP

class RegistroNodoView(APIView):
    """
    Endpoint público para que nuevos nodos (Marcas, Talleres, Bancos) 
    se registren en la PKI de la red federada.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = NodoFederadoSerializer(data=request.data)
        if serializer.is_valid():
            nodo = serializer.save()
            return Response(
                {"mensaje": "Nodo registrado exitosamente", "id_nodo": nodo.id_nodo}, 
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def get(self, request):
        # Lista pública de nodos activos
        nodos = NodoFederado.objects.filter(activo=True)
        serializer = NodoFederadoSerializer(nodos, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class RecepcionEOPView(APIView):
    """
    Recibe el payload canónico de una e-OP recién creada por un Nodo Comitente.
    Valida la firma matemática. Si es válida, crea el RegistroEOP en la MES y arranca el Timelock.
    """
    permission_classes = [permissions.AllowAny] # En producción usaríamos un Custom Permission basado en IP/Firma

    def post(self, request):
        # Guardamos log de la petición (No Repudio)
        log = WebhookLog.objects.create(
            endpoint="/federacion/eop/entrante/",
            metodo="POST",
            payload_recibido=request.data,
            ip_origen=request.META.get("REMOTE_ADDR")
        )

        serializer = EntradaEOPSerializer(data=request.data)
        if serializer.is_valid():
            data = serializer.validated_data
            
            # 1. Crear el Registro en la Gobernanza (MES)
            RegistroEOP.objects.create(
                uuid_identificador=data['uuid_identificador'],
                hash_seguridad=data['hash_seguridad'],
                comitente_cuit=data['comitente_cuit'],
                tallerista_cuit=data['tallerista_cuit'],
                monto_total_uci=data['monto_total_uci'],
                timelock_vencimiento=timezone.now() + datetime.timedelta(hours=48),
                estado="en_revision"
            )

            # Actualizamos el log indicando que la firma criptográfica pasó la prueba matemática
            log.firma_verificada = True
            log.status_code_devuelto = 201
            log.save()

            # (Acá internamente un Celery Task le avisaría al Nodo Tallerista que tiene una orden nueva)
            return Response({"mensaje": "e-OP recibida e inyectada en la MES", "estado": "en_revision"}, status=status.HTTP_201_CREATED)
        
        # Falló validación (Posible manipulación de hash o firma inválida)
        log.status_code_devuelto = 400
        log.save()
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class RecepcionFirmaEtapaView(APIView):
    """
    Recibe un webhook de un PTF o Tallerista aprobando una etapa.
    Valida firma, GPS y procede a afectar el RegistroEOP.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, uuid):
        log = WebhookLog.objects.create(
            endpoint=f"/federacion/eop/{uuid}/firma/",
            metodo="POST",
            payload_recibido=request.data,
            ip_origen=request.META.get("REMOTE_ADDR")
        )

        # Inyectamos el UUID de la URL en los datos
        data = request.data.copy()
        data['eop_uuid'] = uuid

        serializer = FirmaEtapaSerializer(data=data)
        if serializer.is_valid():
            vd = serializer.validated_data
            
            try:
                registro = RegistroEOP.objects.get(uuid_identificador=vd['eop_uuid'])
            except RegistroEOP.DoesNotExist:
                return Response({"error": "e-OP no encontrada en la MES"}, status=status.HTTP_404_NOT_FOUND)

            # Lógica de aprobación según actor
            if vd['actor_rol'] == 'ptf':
                # Si el PTF firmó, salteamos el timelock y aplicamos Aprobación Exprés
                registro.estado = "aprobado_expres"
                registro.save()
                
                # (Acá Celery llamaría a apps.tesoreria.services.EscrowService.liberar_hito(uuid))
            
            log.firma_verificada = True
            log.status_code_devuelto = 200
            log.save()

            return Response({"mensaje": f"Firma de {vd['actor_rol']} aceptada y procesada."}, status=status.HTTP_200_OK)

        log.status_code_devuelto = 400
        log.save()
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
