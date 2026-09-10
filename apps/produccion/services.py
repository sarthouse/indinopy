from django.db import transaction
from django.utils import timezone
import datetime
from decimal import Decimal
from django.contrib.contenttypes.models import ContentType

from apps.produccion.models import (
    OrdenProduccion,
    OPInsumoRequerido,
    OPEtapaTracking
)
from apps.inventario.models import Ubicacion, MovimientoStock, LineaMovimientoStock
from apps.inventario.services import StockService

def _obtener_ubicaciones_base():
    almacen, _ = Ubicacion.objects.get_or_create(
        tipo="interna", defaults={"nombre": "Almacén Principal", "activa": True}
    )
    produccion, _ = Ubicacion.objects.get_or_create(
        tipo="produccion", defaults={"nombre": "Fábrica (Virtual)", "activa": True}
    )
    return almacen, produccion


class ProduccionService:
    @staticmethod
    def calcular_insumos_requeridos_op(op):
        receta = op.receta
        if not receta:
            return

        op.insumos_requeridos.all().delete()
        insumos_a_crear = []
        variaciones_orden = list(op.variaciones.prefetch_related("producto__valores_atributo"))

        for ri in receta.insumos.prefetch_related("variantes_destino").all():
            filtros_variante = ri.variantes_destino.all()
            if not filtros_variante.exists():
                cantidad_total_aplicable = Decimal(op.cantidad_total)
            else:
                cantidad_total_aplicable = Decimal(0)
                ids_atributos_requeridos = set(filtros_variante.values_list("id", flat=True))

                for var in variaciones_orden:
                    atributos_producto = set(var.producto.valores_atributo.values_list("id", flat=True))
                    if ids_atributos_requeridos.issubset(atributos_producto):
                        cantidad_total_aplicable += Decimal(var.cantidad)

            if cantidad_total_aplicable > 0:
                cantidad_teorica = ri.cantidad * cantidad_total_aplicable
                insumos_a_crear.append(
                    OPInsumoRequerido(
                        op=op,
                        insumo=ri.insumo,
                        origen="empresa" if op.tipo == "interna" else "fabrica",
                        cantidad_teorica=cantidad_teorica,
                    )
                )

        if insumos_a_crear:
            OPInsumoRequerido.objects.bulk_create(insumos_a_crear)

    @staticmethod
    @transaction.atomic
    def instanciar_desde_receta(op):
        if not op.receta:
            return
        
        etapas_a_crear = []
        for re in op.receta.etapas.all():
            etapas_a_crear.append(
                OPEtapaTracking(op=op, etapa_origen=re, estado="pendiente")
            )
        if etapas_a_crear:
            OPEtapaTracking.objects.bulk_create(etapas_a_crear)

    @staticmethod
    @transaction.atomic
    def confirmar_op(op):
        if op.estado != "borrador":
            return
            
        op.estado = "confirmado"
        op.save(update_fields=["estado"])

        ProduccionService.calcular_insumos_requeridos_op(op)
        op.sellar_hash_seguridad()

        almacen, ubicacion_produccion = _obtener_ubicaciones_base()
        ct = ContentType.objects.get_for_model(op)

        remito_insumos, _ = MovimientoStock.objects.get_or_create(
            numero=f"RES-{op.numero}",
            defaults={
                "tipo": "traslado",
                "estado": "confirmado",
                "ubicacion_origen": almacen,
                "ubicacion_destino": ubicacion_produccion,
                "content_type_origen": ct,
                "object_id_origen": op.id,
                "documento_origen": op.numero,
                "observaciones": f"Reserva de insumos para OP {op.numero}",
            },
        )

        for req in op.insumos_requeridos.filter(origen="empresa"):
            linea = LineaMovimientoStock.objects.create(
                movimiento=remito_insumos,
                producto=req.insumo,
                cantidad=req.cantidad_teorica,
                cantidad_hecha=req.cantidad_teorica,
                ubicacion_origen=almacen,
                ubicacion_destino=ubicacion_produccion,
                estado="borrador",
                referencia=f"Insumo OP {op.numero}",
            )
            StockService.reservar_linea(linea)

        # === Lógica del Sistema Dual (RIGI / e-OP Federada) ===
        if op.es_eop_federada:
            from apps.tesoreria.models import ContratoEscrow, HitoEscrow
            escrow = ContratoEscrow.objects.create(
                eop_uuid=op.uuid_identificador,
                monto_total_uci=op.costo_total_fason,
                estado="borrador",
            )
            HitoEscrow.objects.create(
                contrato=escrow,
                nombre="Hito Final - Entrega Completa",
                porcentaje=Decimal("100.00"),
                estado="bloqueado",
            )

            from apps.mes.models import RegistroEOP
            RegistroEOP.objects.create(
                uuid_identificador=op.uuid_identificador,
                hash_seguridad=op.hash_seguridad,
                comitente_cuit=op.cliente.cuil if op.cliente else "00000000000",
                tallerista_cuit=op.tallerista_principal.cuil if op.tallerista_principal else "00000000000",
                monto_total_uci=op.costo_total_fason,
                timelock_vencimiento=timezone.now() + datetime.timedelta(hours=48),
                estado="en_revision"
            )

            from apps.documentos.models import DocumentoAdjunto
            from django.core.files.base import ContentFile
            payload_str = op.generar_payload_canonico()
            archivo_json = ContentFile(payload_str.encode("utf-8"), name=f"eOP_{op.numero}_canonical.json")
            DocumentoAdjunto.objects.create(
                content_type=ct,
                object_id=op.id,
                nombre=f"Contrato Criptográfico e-OP {op.numero}",
                archivo=archivo_json,
                mimetype="application/json",
                descripcion="Payload canónico inmutable con hash SHA-256 de la Orden de Producción."
            )

    @staticmethod
    @transaction.atomic
    def avanzar_etapa_op(op, nueva_etapa, payload_ptf=None):
        """
        Avanza la OP a un nuevo subestado (ej: 'cortado' -> 'aparado').
        Usa el Sistema Dual: si es federada, exige validación PTF.
        """
        if op.estado != "confirmado":
            raise ValueError("Solo se pueden avanzar OPs confirmadas.")
            
        if op.es_eop_federada:
            # 🛑 Flujo Federado RIGI (Alta Seguridad)
            if not payload_ptf:
                raise ValueError("Las e-OP federadas requieren firma y coordenadas GPS del PTF para avanzar.")
            
            # TODO: Llamar al PTFService para verificar_firma_campo(payload_ptf, PTF)
            # TODO: Llamar a EscrowService para liberar_hito()
            
            # Por ahora solo actualizamos el estado simulando éxito
            op.subestado = nueva_etapa
            op.save(update_fields=["subestado"])
        else:
            # 🟢 Flujo Privado (Simple)
            op.subestado = nueva_etapa
            op.save(update_fields=["subestado"])

    @staticmethod
    @transaction.atomic
    def finalizar_op(op):
        if op.estado != "confirmado":
            return
            
        op.estado = "finalizado"
        op.save(update_fields=["estado"])

        almacen, ubicacion_produccion = _obtener_ubicaciones_base()
        remito_insumos = MovimientoStock.objects.filter(numero=f"RES-{op.numero}").first()
        if remito_insumos:
            remito_insumos.estado = "finalizado"
            remito_insumos.save()
            for linea in remito_insumos.lineas.filter(estado="reservado"):
                StockService.realizar_linea(linea, estado_viejo="reservado")

        variaciones_pendientes = [var for var in op.variaciones.all() if var.cantidad_pendiente > 0]
        if variaciones_pendientes:
            ct = ContentType.objects.get_for_model(op)
            remito_ingreso = MovimientoStock.objects.create(
                numero=f"ING-{op.numero}-FINAL",
                tipo="recepcion",
                estado="finalizado",
                ubicacion_origen=ubicacion_produccion,
                ubicacion_destino=almacen,
                contacto=op.cliente,
                content_type_origen=ct,
                object_id_origen=op.id,
                documento_origen=op.numero,
                observaciones=f"Ingreso de producto terminado de OP {op.numero}",
            )

            for variacion in variaciones_pendientes:
                qty_a_ingresar = variacion.cantidad_pendiente
                variacion.cantidad_producida += qty_a_ingresar
                variacion.save()

                linea_ingreso = LineaMovimientoStock.objects.create(
                    movimiento=remito_ingreso,
                    producto=variacion.producto,
                    cantidad=Decimal(qty_a_ingresar),
                    cantidad_hecha=Decimal(qty_a_ingresar),
                    ubicacion_origen=ubicacion_produccion,
                    ubicacion_destino=almacen,
                    estado="borrador",
                    referencia=f"Finalización OP {op.numero}",
                )
                StockService.realizar_linea(linea_ingreso, estado_viejo="borrador")

            total_producido = sum(v.cantidad_producida for v in op.variaciones.all())
            OrdenProduccion.objects.filter(pk=op.pk).update(cantidad_producida=total_producido)

    @staticmethod
    @transaction.atomic
    def cancelar_op(op):
        if op.estado not in ["borrador", "confirmado"]:
            return
            
        estado_anterior = op.estado
        op.estado = "cancelado"
        op.save(update_fields=["estado"])

        if estado_anterior == "confirmado":
            remito_insumos = MovimientoStock.objects.filter(numero=f"RES-{op.numero}").first()
            if remito_insumos:
                remito_insumos.estado = "cancelado"
                remito_insumos.save()
                for linea in remito_insumos.lineas.filter(estado="reservado"):
                    StockService.cancelar_linea(linea, estado_viejo="reservado")
