import datetime
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.http import HttpResponseForbidden
from apps.contactos.models import Contacto
from django.conf import settings
from decimal import Decimal

_ROLE = getattr(settings, "NODE_ROLE", "DEV")

# Módulos del Nodo MES (Gobernanza y FDI)
if _ROLE in ["MES", "DEV"]:
    from apps.mes.models import RegistroEOP, ScoringTallerista
    from apps.mes.services import PTFService
    from apps.eop.models import ContratoEOP, EOPHitoEscrow
else:
    RegistroEOP = ScoringTallerista = PTFService = ContratoEOP = EOPHitoEscrow = None

# Módulos de Nodos ERP (Comitente / Tallerista)
if _ROLE in ["COMITENTE", "TALLERISTA", "DEV"]:
    from apps.inventario.models import MovimientoStock, ProductoTemplate, Ubicacion
    from apps.produccion.models import (
        OPEtapaTracking,
        OPParteProduccion,
        OPParteProduccionLinea,
        OrdenProduccion,
        Receta,
        RecetaEtapa,
    )
else:
    MovimientoStock = ProductoTemplate = Ubicacion = None
    OPEtapaTracking = OPParteProduccion = OPParteProduccionLinea = None
    OrdenProduccion = Receta = RecetaEtapa = None

from .models import NodoFederado, NovedadFederada, WebhookLog
from .serializers import (
    EntradaEOPSerializer,
    FirmaEtapaSerializer,
    NodoFederadoSerializer,
)
from .tasks import liberar_hito_escrow_async, notificar_tallerista_nueva_eop


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

    def dispatch(self, request, *args, **kwargs):
        if _ROLE not in ["MES", "DEV"]:
            return HttpResponseForbidden(
                "Esta vista de gobernanza solo está habilitada para el Nodo MES."
            )
        return super().dispatch(request, *args, **kwargs)

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

            # 1. Consultar ScoringTallerista local (Nodo MES)
            tallerista_cuit = data["tallerista_cuit"]
            posee_sbd = False
            score_global = Decimal("0.00")

            try:
                tallerista = Contacto.objects.get(cuil=tallerista_cuit)
                scoring = ScoringTallerista.objects.filter(
                    tallerista=tallerista
                ).first()
                if scoring:
                    posee_sbd = scoring.posee_sbd
                    score_global = scoring.score_global_calculado
            except Contacto.DoesNotExist:
                pass

            # 2. Evaluación de Fast-Track (Protocolo de e-OP Espejo y Duplicación Express - Addenda 1)
            payload_canonico = data.get("payload_canonico") or {}
            vector_costos = payload_canonico.get("vector_costos", {})
            merkle_root_bom = payload_canonico.get("merkle_root_bom", "")

            # Criterio A: Réplica técnica en los últimos 12 meses (mismos insumos Merkle Root y mismo taller/marca)
            hace_un_ano = timezone.now() - datetime.timedelta(days=365)
            es_replica_tecnica = False
            if merkle_root_bom:
                uuids_aprobados = RegistroEOP.objects.filter(
                    comitente_cuit=data["comitente_cuit"],
                    tallerista_cuit=tallerista_cuit,
                    creado_en__gte=hace_un_ano,
                    estado__in=["aprobado_expres", "aprobado_silencio"],
                ).values_list("uuid_identificador", flat=True)

                if uuids_aprobados:
                    es_replica_tecnica = ContratoEOP.objects.filter(
                        uuid_identificador__in=uuids_aprobados,
                        merkle_root_bom=merkle_root_bom,
                    ).exists()

            # Criterio B: Tallerista con Scoring de Excelencia (> 90.00)
            es_score_alto = score_global > Decimal("90.00")


            if es_replica_tecnica or es_score_alto:
                estado_inicial = "aprobado_expres"
                timelock = timezone.now() + datetime.timedelta(hours=2)  # Fast-Track 2 horas
            else:
                estado_inicial = "en_revision"
                timelock = timezone.now() + datetime.timedelta(hours=48)  # Plazo ordinario 48 horas

            # 3. Crear el Registro en la Gobernanza (MES)
            registro = RegistroEOP.objects.create(
                uuid_identificador=data["uuid_identificador"],
                hash_seguridad=data["hash_seguridad"],
                comitente_cuit=data["comitente_cuit"],
                tallerista_cuit=tallerista_cuit,
                monto_total_uci=data["monto_total_uci"],
                timelock_vencimiento=timelock,
                estado=estado_inicial,
            )


            # 4. Crear Contrato Escrow en el FDI (Nodo MES/EOP)
            payload_canonico = data.get("payload_canonico") or {}
            vector_costos = payload_canonico.get("vector_costos", {})

            # Extraer y estructurar la multifirma obligatoria (Comitente + Tallerista)
            firmas_escrow = {
                "comitente": {
                    "cuit": data["comitente_cuit"],
                    "firma_hex": data["firma_comitente"],
                    "clave_publica": data["clave_publica_comitente"],
                    "timestamp": timezone.now().isoformat(),
                },
                "tallerista": {
                    "cuit": tallerista_cuit,
                    "firma_hex": data.get("firma_tallerista") or payload_canonico.get("firmas_digitales", {}).get("tallerista", {}).get("firma_hex", ""),
                    "timestamp": timezone.now().isoformat(),
                }
            }

            escrow = ContratoEOP.objects.create(
                uuid_identificador=data["uuid_identificador"],
                costo_mod=Decimal(str(vector_costos.get("mod_servicios", vector_costos.get("mod", data["monto_total_uci"])))),
                costo_bom=Decimal(str(vector_costos.get("insumos_bom", vector_costos.get("bom", "0.00")))),
                costo_fdi=Decimal(str(vector_costos.get("canon_fdi_mes", vector_costos.get("fdi", "0.00")))),
                es_sello_buen_diseno=bool(payload_canonico.get("es_sello_buen_diseno", posee_sbd)),
                merkle_root_bom=payload_canonico.get("merkle_root_bom", ""),
                firmas_digitales=firmas_escrow,
                estado_escrow="solicitado",
            )

            # Generación Dinámica de Hitos Escrow a partir del payload
            hitos_payload = data.get("cronograma_escrow_hitos") or payload_canonico.get("cronograma_escrow_hitos")
            if hitos_payload:
                for idx, hito_info in enumerate(hitos_payload):
                    porc = Decimal(str(hito_info.get("porcentaje_tramo", "0.00")))
                    nombre = hito_info.get("nombre") or f"Hito {idx + 1}"
                    req_ptf = bool(hito_info.get("requiere_auditoria_ptf", True))
                    req_arca = bool(hito_info.get("requiere_verificacion_arca", False))
                    uuid_hito = hito_info.get("uuid")

                    h_kwargs = {
                        "contrato": escrow,
                        "nombre": nombre,
                        "porcentaje_tramo": porc,
                        "estado": "bloqueado",
                        "requiere_auditoria_ptf": req_ptf,
                        "requiere_verificacion_arca": req_arca,
                    }
                    if uuid_hito:
                        h_kwargs["uuid_identificador"] = uuid_hito
                    EOPHitoEscrow.objects.create(**h_kwargs)
            else:
                # Fallback: Tríada Canónica Dictaminada por la MES (ComisionService)
                try:
                    from apps.mes.services import ComisionService
                    pauta_mes = ComisionService.obtener_pauta_escrow(es_sello_buen_diseno=posee_sbd)
                    porcentaje_hito_cero = pauta_mes["porcentaje_cero"]
                    nombre_cero = pauta_mes["etiqueta_cero"]
                    porcentaje_final = pauta_mes["porcentaje_final"]
                except Exception:
                    porcentaje_hito_cero = Decimal("50.00") if posee_sbd else Decimal("35.00")
                    nombre_cero = f"Hito Cero - Adelanto Operativo de Arranque ({'SBD 50%' if posee_sbd else '35%'})"
                    porcentaje_final = Decimal("20.00")

                if (porcentaje_hito_cero + porcentaje_final) >= Decimal("100.00"):
                    porcentaje_final = max(Decimal("10.00"), Decimal("100.00") - porcentaje_hito_cero - Decimal("10.00"))

                porcentaje_avance_total = Decimal("100.00") - porcentaje_hito_cero - porcentaje_final

                # 1. Hito Cero (dictaminado por la MES)
                EOPHitoEscrow.objects.create(
                    contrato=escrow,
                    nombre=nombre_cero,
                    porcentaje_tramo=porcentaje_hito_cero,
                    estado="bloqueado",
                    requiere_auditoria_ptf=False,
                    requiere_verificacion_arca=False,
                )

                # 2. Hitos de Avance Productivo
                etapas_in = payload_canonico.get("etapas_productivas", [])
                if etapas_in:
                    total_mod = sum(Decimal(str(e.get("costo_servicio", "0.00"))) for e in etapas_in)
                    porcentaje_acumulado = Decimal("0.00")
                    for idx, et in enumerate(etapas_in):
                        es_ultima = (idx == len(etapas_in) - 1)
                        nombre_et = et.get("servicio") or f"Etapa {idx + 1}"
                        orden = et.get("orden", idx + 1)

                        if es_ultima:
                            porc_e = porcentaje_avance_total - porcentaje_acumulado
                        else:
                            if total_mod > 0:
                                costo_e = Decimal(str(et.get("costo_servicio", "0.00")))
                                porc_e = round((costo_e / total_mod) * porcentaje_avance_total, 2)
                            else:
                                porc_e = round(porcentaje_avance_total / Decimal(len(etapas_in)), 2)
                            porcentaje_acumulado += porc_e

                        EOPHitoEscrow.objects.create(
                            contrato=escrow,
                            nombre=f"Hito {orden} - Avance: {nombre_et}",
                            porcentaje_tramo=porc_e,
                            estado="bloqueado",
                            requiere_auditoria_ptf=True,
                            requiere_verificacion_arca=False,
                        )

                # 3. Hito Final de Entrega y Cierre Fiscal
                EOPHitoEscrow.objects.create(
                    contrato=escrow,
                    nombre="Hito Final - Entrega Conformada y Cierre Fiscal",
                    porcentaje_tramo=porcentaje_final,
                    estado="bloqueado",
                    requiere_auditoria_ptf=True,
                    requiere_verificacion_arca=True,
                )

            # 5. Ejecutar Adelanto si aplicó Fast-Track
            if estado_inicial == "aprobado_expres":
                PTFService._liberar_escrow_por_eop(registro)

            # Actualizamos el log indicando que la firma criptográfica pasó la prueba matemática
            log.firma_verificada = True
            log.status_code_devuelto = 201
            log.save()

            # Tarea Celery Asincrónica: Notificar al Taller
            notificar_tallerista_nueva_eop.delay(
                str(data["uuid_identificador"]), data["tallerista_cuit"], request.data
            )

            return Response(
                {
                    "mensaje": "e-OP recibida, Escrow creado e inyectada en la MES",
                    "estado": estado_inicial,
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

    def dispatch(self, request, *args, **kwargs):
        if _ROLE not in ["MES", "DEV"]:
            return HttpResponseForbidden("Esta vista de gobernanza solo está habilitada para el Nodo MES.")
        return super().dispatch(request, *args, **kwargs)

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

    def dispatch(self, request, *args, **kwargs):
        if _ROLE not in ["COMITENTE", "TALLERISTA", "DEV"]:
            return HttpResponseForbidden("Esta vista ERP solo está habilitada para Nodos Comitente o Tallerista.")
        return super().dispatch(request, *args, **kwargs)

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
            cuil=cuit_emisor,
            defaults={
                "codigo": f"CLI-{cuit_emisor}"[:20],
                "nombre": payload.get("razon_social_comitente", "Marca Desconocida"),
                "tipo": "CLIENTE",
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
        template_defecto, _ = ProductoTemplate.objects.get_or_create(
            nombre=f"Producto Fason {op_espejo.numero}",
            defaults={"tipo": "producto"},
        )
        receta_espejo, _ = Receta.objects.get_or_create(
            producto_template=template_defecto,
            nombre_version=f"ESP-{op_espejo.numero}",
        )
        etapas_payload = payload.get("etapas", [])
        for i, etapa_data in enumerate(etapas_payload):
            servicio, _ = ProductoTemplate.objects.get_or_create(
                nombre=etapa_data.get("servicio_nombre", "Servicio Genérico"),
                tipo="servicio",
            )
            receta_etapa, _ = RecetaEtapa.objects.get_or_create(
                receta=receta_espejo,
                servicio=servicio,
                defaults={"orden_ejecucion": i + 1},
            )

            OPEtapaTracking.objects.create(
                op=op_espejo,
                etapa_origen=receta_etapa,
                tallerista_asignado=None,  # Somos nosotros mismos, o nuestros empleados
                estado="pendiente",
            )

        # 4. Remito de Ingreso de Mercadería en Custodia
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


class ParteProduccionWebhookReceiverAPIView(APIView):
    """
    Recibe un "Parte de Producción" (avance físico) emitido por el Nodo Taller
    y replica el progreso en el Nodo Marca.
    """

    def dispatch(self, request, *args, **kwargs):
        if _ROLE not in ["COMITENTE", "TALLERISTA", "DEV"]:
            return HttpResponseForbidden("Esta vista ERP solo está habilitada para Nodos Comitente o Tallerista.")
        return super().dispatch(request, *args, **kwargs)

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

        # Validación PoPW (Ubicación GPS reportada por el taller satélite)
        lat = payload.get("gps_lat")
        lon = payload.get("gps_lon")
        gps_point = None
        if lat is not None and lon is not None:
            from django.contrib.gis.geos import Point
            gps_point = Point(float(lon), float(lat), srid=4326)

        taller_etapa = etapa_tracking.tallerista_asignado if etapa_tracking else op.taller_gestor
        if taller_etapa and taller_etapa.ubicacion_catastral and gps_point:
            distancia_grados = taller_etapa.ubicacion_catastral.distance(gps_point)
            distancia_metros = distancia_grados * 111320
            if distancia_metros > 350:  # Tolerancia geodésica de 350 metros
                return Response(
                    {"error": f"Rechazo PoPW: Coordenadas fuera de la planta homologada ({int(distancia_metros)}m de desvío)"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # 4. Crear el Parte de Producción Espejo
        parte_espejo = OPParteProduccion.objects.create(
            op=op,
            etapa_tracking=etapa_tracking,
            numero_parte=f"EXT-{payload.get('numero_parte', 'SD')}",
            ubicacion_gps_declarada=gps_point,
            hash_validacion_biometrica=payload.get("hash_biometrico", ""),
        )

        # 5. Replicar las líneas producidas
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


class PollingNovedadesAPIView(APIView):
    """
    Endpoint para el paradigma On-Premise con Polling (Pull).
    Permite que un nodo (Tallerista o Marca sin IP pública) consulte a la MES
    si hay Webhooks/Eventos pendientes en su bandeja de entrada.
    Requiere que el nodo envíe su CUIT en el Header X-CUIT.
    """

    permission_classes = [permissions.AllowAny]

    def dispatch(self, request, *args, **kwargs):
        if _ROLE not in ["COMITENTE", "TALLERISTA", "DEV"]:
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden("Esta vista de polling está habilitada para Nodos ERP (Comitente/Taller).")
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        cuit = request.headers.get("X-CUIT")
        if not cuit:
            return Response(
                {"error": "Header X-CUIT requerido"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            nodo = NodoFederado.objects.get(cuit=cuit)
        except NodoFederado.DoesNotExist:
            return Response(
                {"error": "Nodo no registrado en la red"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Buscar novedades no leídas para este nodo
        novedades = NovedadFederada.objects.filter(nodo_destino=nodo, leido=False)

        payloads = []
        for nov in novedades:
            payloads.append(
                {
                    "novedad_id": nov.id,
                    "tipo_evento": nov.tipo_evento,
                    "timestamp": nov.creado_en.isoformat(),
                    "payload": nov.payload,
                }
            )

        return Response(
            {"pendientes": len(payloads), "novedades": payloads},
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        """
        El Nodo llama a este endpoint para marcar como recibidas las novedades (ACK),
        así no se le envían de nuevo en el próximo GET.
        """
        cuit = request.headers.get("X-CUIT")
        if not cuit:
            return Response(
                {"error": "Header X-CUIT requerido"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            nodo = NodoFederado.objects.get(cuit=cuit)
        except NodoFederado.DoesNotExist:
            return Response(
                {"error": "Nodo no registrado en la red"},
                status=status.HTTP_404_NOT_FOUND,
            )

        novedades_ids = request.data.get("novedades_ids", [])
        if novedades_ids:
            NovedadFederada.objects.filter(
                id__in=novedades_ids, nodo_destino=nodo
            ).update(leido=True, fecha_lectura=timezone.now())

        return Response({"status": "ok"}, status=status.HTTP_200_OK)


class TarifarioConvenioAPIView(APIView):
    """
    Endpoint público federado para consultar el Tarifario Homologado de Convenio en UCI.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        from apps.mes.models import TarifaConvenio
        tarifas = TarifaConvenio.objects.filter(activo=True).values(
            "codigo_universal", "servicio_nombre", "precio_referencia_uci", "vigencia_desde"
        )
        return Response(list(tarifas), status=status.HTTP_200_OK)


class PautaEscrowPublicaAPIView(APIView):
    """
    Endpoint público federado para que los nodos Comitentes y Talleristas
    consulten la pauta de porcentajes de Escrow dictaminada por la MES
    (Hito Cero estándar, Sello Buen Diseño e Hito Final ARCA).
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        from apps.mes.services import ComisionService
        sbd_param = request.query_params.get("sello_buen_diseno", "false").lower() in ["true", "1", "t", "yes"]
        comision_id = request.query_params.get("comision_id")
        
        pauta = ComisionService.obtener_pauta_escrow(
            es_sello_buen_diseno=sbd_param,
            comision_id=comision_id,
        )
        return Response(pauta, status=status.HTTP_200_OK)



class CRLAPIView(APIView):
    """
    Lista de Revocación de Certificados (CRL) de la MES.
    Permite validar si la credencial de un PTF fue revocada.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        from apps.mes.services import CRLService
        return Response(CRLService.obtener_crl_completa(), status=status.HTTP_200_OK)


class BoletinOficialPublicoAPIView(APIView):
    """
    Publicación y descarga del Boletín Oficial Sectorial de la MES.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, numero_edicion=None):
        from apps.mes.models import EdicionBoletinSectorial
        from apps.mes.reports.boletin_report import BoletinSectorialPDFReport

        if numero_edicion:
            boletin = EdicionBoletinSectorial.objects.filter(
                numero_edicion=numero_edicion, publicada=True
            ).first()
            if not boletin:
                return Response({"error": "Edición no encontrada"}, status=status.HTTP_404_NOT_FOUND)

            # Si piden formato PDF
            if request.GET.get("format") == "pdf":
                reporte = BoletinSectorialPDFReport(boletin=boletin)
                return reporte.to_http_response(inline=True)

            return Response({
                "numero_edicion": boletin.numero_edicion,
                "fecha_publicacion": boletin.fecha_publicacion.isoformat(),
                "titulo": boletin.titulo,
                "sumario": boletin.sumario_resoluciones,
                "hash_seguridad": boletin.hash_seguridad_publicacion,
                "firma_mes": boletin.firma_mes,
            }, status=status.HTTP_200_OK)

        # Listado de boletines públicos
        boletines = EdicionBoletinSectorial.objects.filter(publicada=True).values(
            "numero_edicion", "fecha_publicacion", "titulo", "hash_seguridad_publicacion"
        )
        return Response(list(boletines), status=status.HTTP_200_OK)


class ClearingPendientesAPIView(APIView):
    """
    Endpoint fiduciario: consulta y descarga de lotes batch BAPRO para tramos de escrow liberados.
    Permite exportar en JSON o en texto plano (.txt) estandarizado.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        from apps.mes.services import ClearingBAPROService
        from django.http import HttpResponse

        hitos_pendientes = ClearingBAPROService.obtener_hitos_pendientes_clearing()

        if request.GET.get("format") == "txt":
            contenido_txt = ClearingBAPROService.generar_lote_clearing_txt(hitos_pendientes)
            fecha_lote = timezone.now().strftime("%Y%m%d_%H%M")
            response = HttpResponse(contenido_txt, content_type="text/plain")
            response["Content-Disposition"] = f'attachment; filename="clearing_bapro_{fecha_lote}.txt"'
            return response

        data = []
        for hito in hitos_pendientes:
            taller = None
            contrato = hito.contrato
            if contrato.orden_produccion_local and contrato.orden_produccion_local.taller_gestor:
                taller = contrato.orden_produccion_local.taller_gestor

            data.append({
                "hito_id": hito.id,
                "hito_nombre": hito.nombre,
                "porcentaje_tramo": str(hito.porcentaje_tramo),
                "eop_numero": contrato.numero,
                "eop_uuid": str(contrato.uuid_identificador),
                "taller_nombre": taller.nombre if taller else "",
                "taller_cuit": taller.cuil if taller else "",
                "taller_cbu": taller.cbu_alias if taller else "",
            })

        return Response(data, status=status.HTTP_200_OK)


class ClearingCallbackAPIView(APIView):
    """
    Endpoint callback / webhook del banco o fiduciaria:
    Confirma la ejecución del lote batch y concilia los comprobantes en el ERP.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        from apps.mes.services import ClearingBAPROService

        lote_referencia = request.data.get("lote_referencia", f"LOTE-{timezone.now().strftime('%Y%m%d%H%M')}")
        hitos_ids = request.data.get("hitos_ids", [])
        estado_pago = request.data.get("estado_pago", "EXITOSO")

        if not hitos_ids:
            return Response({"error": "Debe especificar la lista de hitos_ids"}, status=status.HTTP_400_BAD_REQUEST)

        resultado = ClearingBAPROService.procesar_callback_clearing(
            lote_referencia=lote_referencia,
            hitos_ids=hitos_ids,
            estado_pago=estado_pago,
        )
        return Response(resultado, status=status.HTTP_200_OK)


# =========================================================================
# COMUNICACIONES OFICIALES Y CÉDULAS ELECTRÓNICAS (STORE-AND-FORWARD)
# =========================================================================


class ComunicacionesOficialesBuzonAPIView(APIView):
    """
    Buzón oficial de notificaciones fehacientes (Domicilio Fiscal/Sectorial Electrónico).
    Filtra cédulas dirigidas al nodo autenticado y oculta los destinatarios CCO a terceros.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        from apps.federacion.models import CedulaDestinatario
        cuit_dest = request.headers.get("X-Node-CUIT") or request.GET.get("cuit")
        if not cuit_dest:
            return Response({"error": "Debe especificar CUIT en header X-Node-CUIT o query param ?cuit="}, status=status.HTTP_400_BAD_REQUEST)

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
            # Destinatarios visibles (TO y CC). CCO sólo se ve a sí mismo.
            visibles = list(com.destinatarios.filter(modo_recepcion__in=["principal", "copia_publica"]).values("cuit_destino", "modo_recepcion"))

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
        from apps.federacion.models import NodoFederado
        from apps.federacion.services import ComunicacionOficialService

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
            return Response({"error": "Faltan parámetros obligatorios (cuit_emisor, asunto, cuerpo)"}, status=status.HTTP_400_BAD_REQUEST)

        nodo_emisor = NodoFederado.objects.filter(cuit=cuit_emisor).first()
        if not nodo_emisor:
            return Response({"error": "Nodo emisor no registrado en el directorio federado"}, status=status.HTTP_404_NOT_FOUND)

        destinatarios_preparados = []
        for d in destinatarios_raw:
            cuit_d = d.get("cuit")
            nodo_d = NodoFederado.objects.filter(cuit=cuit_d).first()
            if nodo_d:
                destinatarios_preparados.append({
                    "nodo_destino": nodo_d,
                    "cuit_destino": cuit_d,
                    "modo": d.get("modo", "principal"),  # principal | copia_publica | copia_oculta
                })

        # 1. Crear el borrador
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

        # 2. Emitir y sellar oficialmente
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
        from apps.federacion.services import ComunicacionOficialService

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
    Si format=pdf, genera el documento oficial renderizado por ComunicacionOficialPDFReport
    adaptando la confidencialidad según el CUIT del observador.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, uuid):
        from apps.federacion.models import ComunicacionOficialFederada
        from apps.federacion.reports.comunicacion_report import ComunicacionOficialPDFReport

        comunicacion = ComunicacionOficialFederada.objects.filter(uuid_identificador=uuid).first()
        if not comunicacion:
            return Response({"error": "Comunicación oficial no encontrada"}, status=status.HTTP_404_NOT_FOUND)

        cuit_observador = request.headers.get("X-Node-CUIT") or request.GET.get("cuit")

        if request.GET.get("format") == "pdf":
            reporte = ComunicacionOficialPDFReport(
                comunicacion=comunicacion,
                cuit_observador=cuit_observador,
            )
            return reporte.to_http_response(inline=True)

        # Retorno JSON
        es_emisor = (cuit_observador == comunicacion.cuit_emisor) or (cuit_observador is None)
        destinatarios_qs = comunicacion.destinatarios.all()
        if not es_emisor:
            # Filtrar solo visibles + el propio observador si es CCO
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
    Calcula el hash SHA-256 en chunks y lo sella en el metadato del documento.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, uuid):
        from apps.federacion.models import ComunicacionOficialFederada
        from apps.federacion.services import ComunicacionOficialService

        comunicacion = ComunicacionOficialFederada.objects.filter(uuid_identificador=uuid).first()
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
    Descarga un archivo adjunto con cabecera de verificación SHA-256 (X-Digest-SHA256).
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, uuid, adjunto_uuid):
        from django.http import FileResponse
        from apps.federacion.models import ComunicacionOficialFederada
        from apps.documentos.models import DocumentoAdjunto

        comunicacion = ComunicacionOficialFederada.objects.filter(uuid_identificador=uuid).first()
        if not comunicacion:
            return Response({"error": "Comunicación oficial no encontrada"}, status=status.HTTP_404_NOT_FOUND)

        adjunto = comunicacion.adjuntos.filter(uuid=adjunto_uuid).first()
        if not adjunto or not adjunto.archivo:
            return Response({"error": "Archivo adjunto no encontrado en esta comunicación"}, status=status.HTTP_404_NOT_FOUND)

        # Buscar el hash correspondiente
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
    Endpoint receptor de Webhooks para nodos federados (Push):
    Recibe la cédula enviada por el nodo emisor o la MES, verifica la firma Ed25519
    y la almacena en el buzón local del ERP como Cédula/Comunicación recibida.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        from nacl.signing import VerifyKey
        from nacl.exceptions import BadSignatureError
        from apps.federacion.models import NodoFederado, ComunicacionOficialFederada, CedulaDestinatario, WebhookLog
        from apps.base.models import ConfiguracionEmpresa

        data = request.data
        cuit_emisor = data.get("cuit_emisor")
        hash_payload = data.get("hash_seguridad_payload")
        firma_ed25519 = data.get("firma_emisor_ed25519")

        # Registrar log inmutable del webhook entrante
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

        # Validar firma Ed25519 contra la clave pública del nodo emisor
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

        # Espejar la comunicación en el nodo receptor
        uuid_str = data.get("uuid_identificador")
        comunicacion, _created = ComunicacionOficialFederada.objects.get_or_create(
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

        # Crear o actualizar la cédula del receptor local
        cuit_destino = data.get("cuit_destino")
        empresa_local = ConfiguracionEmpresa.objects.first()
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







