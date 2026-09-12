import datetime
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.db import transaction
from apps.produccion.models import OrdenProduccion
from apps.contactos.models import Contacto

from .models import NodoFederado, WebhookLog
from .serializers import (
    NodoFederadoSerializer,
    EntradaEOPSerializer,
    FirmaEtapaSerializer,
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
                status=status.HTTP_201_CREATED,
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

    permission_classes = [
        permissions.AllowAny
    ]  # En producción usaríamos un Custom Permission basado en IP/Firma

    def post(self, request):
        # Guardamos log de la petición (No Repudio)
        log = WebhookLog.objects.create(
            endpoint="/federacion/eop/entrante/",
            metodo="POST",
            payload_recibido=request.data,
            ip_origen=request.META.get("REMOTE_ADDR"),
        )

        serializer = EntradaEOPSerializer(data=request.data)
        if serializer.is_valid():
            data = serializer.validated_data

            # 1. Crear el Registro en la Gobernanza (MES)
            RegistroEOP.objects.create(
                uuid_identificador=data["uuid_identificador"],
                hash_seguridad=data["hash_seguridad"],
                comitente_cuit=data["comitente_cuit"],
                tallerista_cuit=data["tallerista_cuit"],
                monto_total_uci=data["monto_total_uci"],
                timelock_vencimiento=timezone.now() + datetime.timedelta(hours=48),
                estado="en_revision",
            )

            # Actualizamos el log indicando que la firma criptográfica pasó la prueba matemática
            log.firma_verificada = True
            log.status_code_devuelto = 201
            log.save()

            # Tarea Celery Asincrónica: Notificar al Taller
            from .tasks import notificar_tallerista_nueva_eop

            notificar_tallerista_nueva_eop.delay(
                str(data["uuid_identificador"]), data["tallerista_cuit"], request.data
            )

            return Response(
                {
                    "mensaje": "e-OP recibida e inyectada en la MES",
                    "estado": "en_revision",
                },
                status=status.HTTP_201_CREATED,
            )

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
            ip_origen=request.META.get("REMOTE_ADDR"),
        )

        # Inyectamos el UUID de la URL en los datos
        data = request.data.copy()
        data["eop_uuid"] = uuid

        serializer = FirmaEtapaSerializer(data=data)
        if serializer.is_valid():
            vd = serializer.validated_data

            try:
                registro = RegistroEOP.objects.get(uuid_identificador=vd["eop_uuid"])
            except RegistroEOP.DoesNotExist:
                return Response(
                    {"error": "e-OP no encontrada en la MES"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Lógica de aprobación según actor
            if vd["actor_rol"] == "ptf":
                # Si el PTF firmó, salteamos el timelock y aplicamos Aprobación Exprés
                registro.estado = "aprobado_expres"
                registro.save()

                # Tarea Celery Asincrónica: Liberar Fondos del FDI
                from .tasks import liberar_hito_escrow_async

                liberar_hito_escrow_async.delay(str(registro.uuid_identificador))

            log.firma_verificada = True
            log.status_code_devuelto = 200
            log.save()

            return Response(
                {"mensaje": f"Firma de {vd['actor_rol']} aceptada y procesada."},
                status=status.HTTP_200_OK,
            )

        log.status_code_devuelto = 400
        log.save()
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class EOPWebhookReceiverAPIView(APIView):
    """
    Recibe una e-OP desde otro Nodo (Comitente/Marca) y genera la OP Espejo
    en este Nodo (Taller).
    """

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        payload = request.data

        cuit_emisor = payload.get("cuit_comitente")
        if not cuit_emisor:
            return Response(
                {"error": "CUIT del comitente requerido"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 1. Buscamos/Creamos a la Marca en nuestra libreta de clientes
        cliente_marca, _ = Contacto.objects.get_or_create(
            cuit=cuit_emisor,
            defaults={
                "nombre": payload.get("razon_social_comitente", "Marca Desconocida"),
                "tipo": "cliente",
            },
        )

        # 2. Generamos la OP Espejo (Nosotros somos el fabricante)
        op_espejo = OrdenProduccion.objects.create(
            numero=f"ESP-{payload.get('numero_op_origen')}",
            cliente=cliente_marca,
            tipo="produccion_propia",  # Para nosotros, es producción en nuestra planta
            es_eop_federada=payload.get("es_eop_federada", False),
            cantidad_total=payload.get("cantidad_total", 0),
            estado="confirmado",
            observaciones=f"OP Espejada desde el Nodo {cuit_emisor}",
        )

        # 3. Clonación de Etapas (Tracking)
        # La Marca manda un array de etapas (Aparado, Armado, etc.) que nos tocan.
        from apps.produccion.models import OPEtapaTracking, RecetaEtapa, Receta
        from apps.inventario.models import ProductoTemplate
        
        receta_espejo, _ = Receta.objects.get_or_create(codigo=f"REC-{op_espejo.numero}")
        etapas_payload = payload.get("etapas", [])
        for i, etapa_data in enumerate(etapas_payload):
            servicio, _ = ProductoTemplate.objects.get_or_create(
                nombre=etapa_data.get("servicio_nombre", "Servicio Genérico"),
                tipo='servicio'
            )
            receta_etapa, _ = RecetaEtapa.objects.get_or_create(
                receta=receta_espejo,
                servicio=servicio, 
                defaults={'orden_ejecucion': i+1}
            )
            
            OPEtapaTracking.objects.create(
                op=op_espejo,
                etapa_origen=receta_etapa,
                tallerista_asignado=None, # Somos nosotros mismos, o nuestros empleados
                estado='pendiente'
            )

        # 4. Remito de Ingreso de Mercadería en Custodia
        from apps.inventario.models import MovimientoStock, Ubicacion
        from django.contrib.contenttypes.models import ContentType

        ubicacion_custodia, _ = Ubicacion.objects.get_or_create(
            nombre="Depósito Custodia (Comitentes)", tipo="interna"
        )

        remito_ingreso = MovimientoStock.objects.create(
            numero=f"CUST-{op_espejo.numero}",
            tipo="recepcion",
            estado="borrador",
            ubicacion_destino=ubicacion_custodia,
            contacto=cliente_marca,
            content_type_origen=ContentType.objects.get_for_model(op_espejo),
            object_id_origen=op_espejo.id,
            documento_origen=op_espejo.numero,
            observaciones="Ingreso de Materia Prima en calidad de Custodia (Sin propiedad)",
        )

        # En una versión completa iteraríamos sobre 'payload.get("insumos")' para crear las LineasMovimientoStock

        return Response(
            {"status": "OP Espejo Creada", "op_local": op_espejo.numero},
            status=status.HTTP_201_CREATED,
        )


from apps.produccion.models import OPParteProduccion, OPEtapaTracking
from django.contrib.contenttypes.models import ContentType


class ParteProduccionWebhookReceiverAPIView(APIView):
    """
    Recibe un "Parte de Producción" (avance físico) emitido por el Nodo Taller
    y replica el progreso en el Nodo Marca.
    """

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        payload = request.data

        # 1. Seguridad: Verificar firmas Ed25519 aquí (simulado)
        # 2. Identificar la OP original en nuestro nodo
        numero_op_origen = payload.get("numero_op_origen")
        op = OrdenProduccion.objects.filter(numero=numero_op_origen).first()

        if not op:
            return Response(
                {"error": "OP no encontrada en el Nodo Marca"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 3. Identificar la etapa afectada
        etapa_nombre = payload.get("etapa_servicio_nombre")
        etapa_tracking = op.tracking_etapas.filter(
            etapa_origen__servicio__nombre=etapa_nombre
        ).first()

        # 4. Crear el Parte de Producción Espejo
        parte_espejo = OPParteProduccion.objects.create(
            op=op,
            etapa_tracking=etapa_tracking,
            numero_parte=f"EXT-{payload.get('numero_parte', 'SD')}",
            # En producción se clona el usuario responsable si corresponde o se deja nulo
        )

        # 5. Replicar las líneas producidas
        from apps.produccion.models import OPParteProduccionLinea

        lineas = payload.get("lineas", [])
        for linea_data in lineas:
            # Buscar la OPVariacion correspondiente
            variacion = op.variaciones.filter(
                producto__codigo=linea_data.get("producto_codigo")
            ).first()
            if variacion:
                OPParteProduccionLinea.objects.create(
                    parte=parte_espejo,
                    variacion=variacion,
                    cantidad_primera=linea_data.get("cantidad_primera", 0),
                    cantidad_segunda=linea_data.get("cantidad_segunda", 0),
                    cantidad_descarte=linea_data.get("cantidad_descarte", 0),
                )

                # Actualizar el contador global en la OP
                variacion.cantidad_producida += linea_data.get("cantidad_primera", 0)
                variacion.save()

        # En una implementación real, aquí se llamaría al servicio de inventario
        # para consumir materias primas del depósito de Custodia del taller.

        return Response(
            {"status": "Parte de Producción sincronizado con éxito"},
            status=status.HTTP_201_CREATED,
        )
