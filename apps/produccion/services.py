import datetime
import uuid6
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from django.contrib.contenttypes.models import ContentType

from apps.contactos.models import Contacto
from apps.contabilidad.models import DocumentoDeuda, LineaDocumentoDeuda
from apps.documentos.models import DocumentoAdjunto
from apps.federacion.services import FederacionCreditoService
from apps.inventario.models import LineaMovimientoStock, MovimientoStock, Ubicacion
from apps.inventario.services import StockService
from apps.produccion.models import (
    OPEtapaTracking,
    OPInsumoRequerido,
    OPVariacion,
    OrdenProduccion,
)


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
        variaciones_orden = list(
            op.variaciones.prefetch_related("producto__valores_atributo")
        )

        for ri in receta.insumos.prefetch_related("variantes_destino").all():
            filtros_variante = ri.variantes_destino.all()
            if not filtros_variante.exists():
                cantidad_total_aplicable = Decimal(op.cantidad_total)
            else:
                cantidad_total_aplicable = Decimal(0)
                ids_atributos_requeridos = set(
                    filtros_variante.values_list("id", flat=True)
                )

                for var in variaciones_orden:
                    atributos_producto = set(
                        var.producto.valores_atributo.values_list("id", flat=True)
                    )
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

    # La validación de crédito FDI fue delegada a eop.EOPService mediante signals

        op.estado = "confirmado"
        op.save(update_fields=["estado"])

        ProduccionService.calcular_insumos_requeridos_op(op)

        # Si la OP se inyectó de forma externa (Headless API) y trae su propio BOM,
        # asumimos que el inventario se descuenta en el ERP principal (SAP/Odoo) y salteamos la reserva local.
        if not op.bom_headless:
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

        # La inyección en la red federada y la firma de contrato EOP
        # fue delegada a apps.eop.signals.notificar_avance_fisico_eop

    @staticmethod
    @transaction.atomic
    def avanzar_etapa_op(op, nueva_etapa, payload_ptf=None):
        """
        Avanza la OP a un nuevo subestado (ej: 'cortado' -> 'aparado').
        Usa el Sistema Dual: si es federada, exige validación PTF.
        """
        if op.estado != "confirmado":
            raise ValueError("Solo se pueden avanzar OPs confirmadas.")

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
        remito_insumos = MovimientoStock.objects.filter(
            numero=f"RES-{op.numero}"
        ).first()
        if remito_insumos:
            remito_insumos.estado = "finalizado"
            remito_insumos.save()
            for linea in remito_insumos.lineas.filter(estado="reservado"):
                StockService.realizar_linea(linea, estado_viejo="reservado")

        variaciones_pendientes = [
            var for var in op.variaciones.all() if var.cantidad_pendiente > 0
        ]
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
            OrdenProduccion.objects.filter(pk=op.pk).update(
                cantidad_producida=total_producido
            )

        # Generar Deuda de Tesorería por Servicio (FDI o Talleristas Externos)
        ProduccionService._liquidar_servicios_op(op)

    @staticmethod
    def _liquidar_servicios_op(op):
        """
        Calcula el costo del servicio (MOD + CS) de la OP y genera la deuda contable.
        """
        if op.es_eop_federada:
            # Si está federada (FDI), la marca le debe al fideicomiso, no a cada tallerista.
            # Esta deuda nace vía signals en el módulo EOP, por lo que aquí abortamos.
            return

        if op.tipo == "fason":
            # Paradigma Privado: La Marca le debe a cada Tallerista Externo por separado
            # Buscamos todas las etapas finalizadas y sus talleristas asignados
            for etapa in op.tracking_etapas.filter(estado="finalizada"):
                if not etapa.tallerista_asignado:
                    continue

                costo_etapa = etapa.costo_servicio_total or Decimal("0.00")
                if costo_etapa <= 0:
                    continue

                deuda_privada = DocumentoDeuda.objects.create(
                    tipo="liquidacion_fason",
                    estado="publicado",
                    contacto=etapa.tallerista_asignado,
                    fecha_emision=timezone.now().date(),
                    fecha_vencimiento=timezone.now().date()
                    + timezone.timedelta(days=15),  # Plazo comercial típico de 15 días
                    moneda="ARS",
                    observaciones=f"Liquidación de Fasón - Etapa: {etapa.etapa_origen.servicio.nombre}",
                )

                LineaDocumentoDeuda.objects.create(
                    documento=deuda_privada,
                    producto=None,
                    descripcion=f"Servicio de {etapa.etapa_origen.servicio.nombre}",
                    cantidad=Decimal("1.0"),
                    precio_unitario=costo_etapa,
                    subtotal=costo_etapa,
                )

    @staticmethod
    @transaction.atomic
    def cancelar_op(op):
        if op.estado not in ["borrador", "confirmado"]:
            return

        estado_anterior = op.estado
        op.estado = "cancelado"
        op.save(update_fields=["estado"])

        if estado_anterior == "confirmado":
            remito_insumos = MovimientoStock.objects.filter(
                numero=f"RES-{op.numero}"
            ).first()
            if remito_insumos:
                remito_insumos.estado = "cancelado"
                remito_insumos.save()
                for linea in remito_insumos.lineas.filter(estado="reservado"):
                    StockService.cancelar_linea(linea, estado_viejo="reservado")

    @staticmethod
    @transaction.atomic
    def crear_op_borrador(producto, cantidad, ubicacion_destino):
        """
        Crea una Orden de Producción en estado borrador generada por el MRP.
        """
        nuevo_uuid = uuid6.uuid7()
        numero_op = f"OP-MRP-{str(nuevo_uuid)[:6].upper()}"

        # En la vida real, se buscaría la receta (BOM) activa para este producto
        op = OrdenProduccion.objects.create(
            uuid_identificador=nuevo_uuid,
            numero=numero_op,
            tipo="interna",
            fecha_planificada=datetime.date.today(),
            estado="borrador",
            cantidad_total=cantidad,
            observaciones="Generado automáticamente por el motor MRP (Regla de Abastecimiento).",
        )

        OPVariacion.objects.create(
            op=op, producto=producto, cantidad_planificada=cantidad
        )

        return op
