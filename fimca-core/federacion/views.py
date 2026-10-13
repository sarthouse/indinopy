import datetime
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from base.models import Contacto
from decimal import Decimal
from fdi.models import RegistroEOP, ScoringTallerista
from fdi.services import PTFService
from base.models import ContratoEOP, EOPHitoEscrow

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

            # 1. Consultar SETP / Scoring (Nodo MES)
            tallerista_cuit = data["tallerista_cuit"]
            posee_sbd = False
            score_global = Decimal("70.00")

            try:
                from fdi.services import SETPService
                evaluacion = SETPService.obtener_o_crear_perfil(tallerista_cuit, tipo_actor="taller")
                score_global = evaluacion.score_setp
            except Exception:
                pass

            try:
                tallerista = Contacto.objects.filter(cuil=tallerista_cuit).first()
                if tallerista and hasattr(tallerista, 'scoring_mes'):
                    posee_sbd = tallerista.scoring_mes.posee_sbd
            except Exception:
                pass

            # 2. Evaluación de Fast-Track (Protocolo de e-OP Espejo y Duplicación Express - Addenda 1)
            payload_canonico = data.get("payload_canonico") or {}
            vector_costos = payload_canonico.get("vector_costos", {})
            merkle_root_bom = payload_canonico.get("merkle_root_bom", "")

            # Criterio A: Réplica técnica en los últimos 12 meses (mismos insumos Merkle Root y mismo taller/marca)
            hace_un_ano = timezone.now() - datetime.timedelta(days=365)
            es_replica_tecnica = False
            if merkle_root_bom:
                uuids_aprobados = ContratoEOP.objects.filter(
                    firmas_digitales__comitente__cuit=data["comitente_cuit"],
                    firmas_digitales__tallerista__cuit=tallerista_cuit,
                    created_at__gte=hace_un_ano,
                ).values_list("uuid_identificador", flat=True)

                if uuids_aprobados:
                    es_replica_tecnica = ContratoEOP.objects.filter(
                        uuid_identificador__in=uuids_aprobados,
                        merkle_root_bom=merkle_root_bom,
                    ).exists()

            # Criterio B: Tallerista con Scoring de Excelencia (> 90.00)
            es_score_alto = score_global >= Decimal("90.00")

            if es_replica_tecnica or es_score_alto:
                estado_inicial = "aprobado_expres"
                timelock = timezone.now() + datetime.timedelta(hours=2)  # Fast-Track 2 horas
            else:
                estado_inicial = "en_revision"
                timelock = timezone.now() + datetime.timedelta(hours=48)  # Plazo ordinario 48 horas

            # 3. Crear el Registro de Auditoría en la Gobernanza (MES)
            registro, _ = RegistroEOP.objects.get_or_create(
                uuid_identificador=data["uuid_identificador"],
                defaults={
                    "hash_seguridad": data["hash_seguridad"],
                    "comitente_cuit": data["comitente_cuit"],
                    "tallerista_cuit": tallerista_cuit,
                    "monto_total_uci": data["monto_total_uci"],
                    "timelock_vencimiento": timelock,
                    "estado": estado_inicial,
                }
            )

            # 4. Crear Contrato Escrow en el FDI (Nodo MES/EOP)
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
                    "confesion_deuda_h0_aceptada": bool(payload_canonico.get("clausula_confesion_deuda_h0", True)),
                }
            }

            costo_mod_val = Decimal(str(vector_costos.get("mod_servicios", vector_costos.get("mod", data["monto_total_uci"]))))
            costo_bom_val = Decimal(str(vector_costos.get("insumos_bom", vector_costos.get("bom", "0.00"))))
            costo_fdi_op_val = Decimal(str(vector_costos.get("canon_fdi_operativo", round(costo_mod_val * Decimal("0.015"), 2))))
            costo_fdi_stk_val = Decimal(str(vector_costos.get("canon_fdi_stock", round(costo_bom_val * Decimal("0.005"), 2))))

            plazo_dias = int(payload_canonico.get("plazo_comercial_dias", 60))
            hoy = timezone.now().date()
            fecha_vto = hoy + datetime.timedelta(days=plazo_dias)

            escrow, _ = ContratoEOP.objects.get_or_create(
                uuid_identificador=data["uuid_identificador"],
                defaults={
                    "costo_mod": costo_mod_val,
                    "costo_bom": costo_bom_val,
                    "costo_fdi_operativo": costo_fdi_op_val,
                    "costo_fdi_stock": costo_fdi_stk_val,
                    "moneda_denominacion": payload_canonico.get("moneda_denominacion", "uci"),
                    "plazo_comercial_dias": plazo_dias,
                    "fecha_vencimiento_comercial": fecha_vto,
                    "fecha_vencimiento_recalculada": fecha_vto,
                    "es_sello_buen_diseno": bool(payload_canonico.get("es_sello_buen_diseno", posee_sbd)),
                    "es_justo_a_tiempo": bool(payload_canonico.get("es_justo_a_tiempo", False)),
                    "declaracion_confesion_deuda_hito_cero": bool(payload_canonico.get("clausula_confesion_deuda_h0", True)),
                    "merkle_root_bom": payload_canonico.get("merkle_root_bom", ""),
                    "firmas_digitales": firmas_escrow,
                    "estado_escrow": "solicitado",
                }
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
                    from fdi.services import ComisionService
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

            return Response(
                {"mensaje": f"Firma de {vd['actor_rol']} aceptada y procesada."},
                status=status.HTTP_200_OK,
            )

        log.status_code_devuelto = 400
        log.save()
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PollingNovedadesAPIView(APIView):
    """
    Endpoint para el paradigma On-Premise con Polling (Pull).
    Permite que un nodo (Tallerista o Marca sin IP pública) consulte a la MES
    si hay Webhooks/Eventos pendientes en su bandeja de entrada.
    Requiere que el nodo envíe su CUIT en el Header X-CUIT.
    """

    permission_classes = [permissions.AllowAny]

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
        from fdi.models import TarifaConvenio
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
        from fdi.services import ComisionService
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
        from fdi.services import CRLService
        return Response(CRLService.obtener_crl_completa(), status=status.HTTP_200_OK)


class BoletinOficialPublicoAPIView(APIView):
    """
    Publicación y descarga del Boletín Oficial Sectorial de la MES.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, numero_edicion=None):
        from fdi.models import EdicionBoletinSectorial
        from fdi.reports.boletin_report import BoletinSectorialPDFReport

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
        from fdi.services import ClearingBancarioService
        from django.http import HttpResponse

        hitos_pendientes = ClearingBancarioService.obtener_hitos_pendientes_clearing()

        if request.GET.get("format") == "txt":
            contenido_txt = ClearingBancarioService.generar_lote_clearing_txt(hitos_pendientes)
            fecha_lote = timezone.now().strftime("%Y%m%d_%H%M")
            response = HttpResponse(contenido_txt, content_type="text/plain")
            response["Content-Disposition"] = f'attachment; filename="clearing_fiduciario_{fecha_lote}.txt"'
            return response

        data = []
        for hito in hitos_pendientes:
            contrato = hito.contrato
            taller = getattr(contrato, "tallerista", None)

            data.append({
                "hito_id": hito.id,
                "numero_hito": hito.numero_hito,
                "monto_ars": str(hito.monto_ars),
                "eop_numero": contrato.numero,
                "taller_nombre": taller.nombre if taller else "",
                "taller_cuit": taller.cuit if taller else "",
            })

        return Response(data, status=status.HTTP_200_OK)


class ClearingCallbackAPIView(APIView):
    """
    Endpoint callback / webhook del banco o fiduciaria:
    Confirma la ejecución del lote batch y concilia los comprobantes en el ERP.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        from fdi.services import ClearingBancarioService

        lote_referencia = request.data.get("lote_referencia", f"LOTE-{timezone.now().strftime('%Y%m%d%H%M')}")
        hitos_ids = request.data.get("hitos_ids", [])
        estado_pago = request.data.get("estado_pago", "EXITOSO")

        if not hitos_ids:
            return Response({"error": "Debe especificar la lista de hitos_ids"}, status=status.HTTP_400_BAD_REQUEST)

        resultado = ClearingBancarioService.procesar_callback_clearing(
            lote_referencia=lote_referencia,
            hitos_ids=hitos_ids,
            estado_pago=estado_pago,
        )
        return Response(resultado, status=status.HTTP_200_OK)
