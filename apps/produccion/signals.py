from decimal import Decimal
from django.db import transaction
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from apps.inventario.models import Ubicacion, MovimientoStock, LineaMovimientoStock
from .models import (
    OrdenProduccion,
    OPInsumoRequerido,
    OPEtapaTracking,
    OPEtapaLog,
)


def _obtener_ubicaciones_base():
    """Garantiza que existan las ubicaciones básicas del sistema para mover stock"""
    almacen, _ = Ubicacion.objects.get_or_create(
        tipo="interna", defaults={"nombre": "Almacén Principal", "activa": True}
    )
    produccion, _ = Ubicacion.objects.get_or_create(
        tipo="produccion", defaults={"nombre": "Fábrica (Virtual)", "activa": True}
    )
    return almacen, produccion


# -------------------------------------------------------------------------
# 1. AUTO-INSTANCIAR LA OP DESDE LA RECETA BASE AL CREARSE
# -------------------------------------------------------------------------


def calcular_insumos_requeridos_op(op):
    """
    Calcula los insumos teóricos de una OP cruzando la Receta con la curva de talles/colores (OPVariacion).
    Soporta reglas de variantes: si un insumo tiene filtros en variantes_destino,
    solo se computa para las unidades que coincidan.
    """
    receta = op.receta
    if not receta:
        return

    # Limpiamos cálculos previos si los hubiera
    op.insumos_requeridos.all().delete()

    insumos_a_crear = []
    variaciones_orden = list(op.variaciones.prefetch_related("producto__valores_atributo"))

    for ri in receta.insumos.prefetch_related("variantes_destino").all():
        filtros_variante = ri.variantes_destino.all()

        if not filtros_variante.exists():
            # A) Aplica a TODAS las unidades del lote (ej: Etiquetas, Pegamento)
            cantidad_total_aplicable = Decimal(op.cantidad_total)
        else:
            # B) Aplica SOLO a las variantes que coincidan con los atributos (ej: Tela Roja)
            cantidad_total_aplicable = Decimal(0)
            ids_atributos_requeridos = set(filtros_variante.values_list("id", flat=True))

            for var in variaciones_orden:
                atributos_producto = set(var.producto.valores_atributo.values_list("id", flat=True))
                if ids_atributos_requeridos.issubset(atributos_producto):
                    cantidad_total_aplicable += Decimal(var.cantidad)

        # Si para este lote se fabrican unidades que usen este insumo, lo agregamos
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


@receiver(post_save, sender=OrdenProduccion)
def instanciar_op_desde_receta(sender, instance, created, **kwargs):
    """
    Cuando se crea una OP en borrador, clona automáticamente la lista de materiales
    y la hoja de ruta de etapas.
    """
    if created and instance.receta:
        # A) Calcular insumos teóricos iniciales
        calcular_insumos_requeridos_op(instance)

        # B) Clonar etapas de tracking
        etapas_a_crear = []
        for re in instance.receta.etapas.all():
            etapas_a_crear.append(
                OPEtapaTracking(
                    op=instance,
                    etapa_origen=re,
                    estado="pendiente",
                )
            )
        if etapas_a_crear:
            OPEtapaTracking.objects.bulk_create(etapas_a_crear)


# -------------------------------------------------------------------------
# 2. CAPTURAR ESTADO ANTERIOR DE LA OP
# -------------------------------------------------------------------------
@receiver(pre_save, sender=OrdenProduccion)
def capturar_estado_anterior_op(sender, instance, **kwargs):
    if instance.pk:
        old = OrdenProduccion.objects.filter(pk=instance.pk).values("estado").first()
        instance._old_estado = old["estado"] if old else None
    else:
        instance._old_estado = None


# -------------------------------------------------------------------------
# 3. IMPACTO DE LA OP EN EL INVENTARIO (RESERVAS, CONSUMOS Y ENTRADAS)
# -------------------------------------------------------------------------
@receiver(post_save, sender=OrdenProduccion)
def procesar_transicion_estado_op(sender, instance, created, **kwargs):
    estado_viejo = getattr(instance, "_old_estado", None)
    estado_nuevo = instance.estado

    if estado_viejo == estado_nuevo:
        return

    almacen, ubicacion_produccion = _obtener_ubicaciones_base()

    # A) BORRADOR -> CONFIRMADO: Sellar e-OP con hash y reservar insumos propios
    if estado_nuevo == "confirmado":
        with transaction.atomic():
            instance.sellar_hash_eop()

            # Creamos el remito interno de traslado a producción
            remito_insumos, _ = MovimientoStock.objects.get_or_create(
                numero=f"RES-{instance.numero}",
                defaults={
                    "tipo": "traslado",
                    "estado": "confirmado",
                    "ubicacion_origen": almacen,
                    "ubicacion_destino": ubicacion_produccion,
                    "observaciones": f"Reserva de insumos para OP {instance.numero}",
                },
            )

            # Recalculamos los insumos requeridos exactos tomando la curva de variaciones (OPVariacion)
            calcular_insumos_requeridos_op(instance)

            # Para cada insumo provisto por la empresa, creamos línea en 'reservado'
            # (Nuestra señal de inventario automáticamente actualizará el StockQuant reservado)
            for req in instance.insumos_requeridos.filter(origen="empresa"):
                LineaMovimientoStock.objects.create(
                    movimiento=remito_insumos,
                    producto=req.insumo,
                    cantidad=req.cantidad_teorica,
                    ubicacion_origen=almacen,
                    ubicacion_destino=ubicacion_produccion,
                    estado="reservado",
                    referencia=f"Insumo OP {instance.numero}",
                )

    # B) CONFIRMADO -> FINALIZADO: Consumir insumos e ingresar Producto Terminado
    elif estado_nuevo == "finalizado":
        with transaction.atomic():
            # 1. Efectivizar el consumo de insumos (pasan de reservado a realizado)
            remito_insumos = MovimientoStock.objects.filter(
                numero=f"RES-{instance.numero}"
            ).first()
            if remito_insumos:
                remito_insumos.estado = "finalizado"
                remito_insumos.save()
                for linea in remito_insumos.lineas.filter(estado="reservado"):
                    linea.estado = "realizado"
                    linea.save()

            # 2. Ingresar al stock los productos terminados pendientes de la curva (OPVariacion)
            variaciones_pendientes = [
                var for var in instance.variaciones.all() if var.cantidad_pendiente > 0
            ]
            if variaciones_pendientes:
                remito_ingreso = MovimientoStock.objects.create(
                    numero=f"ING-{instance.numero}-FINAL",
                    tipo="recepcion",
                    estado="finalizado",
                    ubicacion_origen=ubicacion_produccion,
                    ubicacion_destino=almacen,
                    contacto=instance.cliente,
                    documento_origen=instance.numero,
                    observaciones=f"Ingreso de producto terminado de OP {instance.numero}",
                )

                for variacion in variaciones_pendientes:
                    qty_a_ingresar = variacion.cantidad_pendiente
                    variacion.cantidad_producida += qty_a_ingresar
                    variacion.save()

                    LineaMovimientoStock.objects.create(
                        movimiento=remito_ingreso,
                        producto=variacion.producto,
                        cantidad=Decimal(qty_a_ingresar),
                        cantidad_hecha=Decimal(qty_a_ingresar),
                        ubicacion_origen=ubicacion_produccion,
                        ubicacion_destino=almacen,
                        estado="realizado",
                        referencia=f"Finalización OP {instance.numero}",
                    )

                # Actualizamos el total producido en base de datos sin disparar recursión
                total_producido = sum(v.cantidad_producida for v in instance.variaciones.all())
                OrdenProduccion.objects.filter(pk=instance.pk).update(cantidad_producida=total_producido)

    # C) CANCELACIÓN: Si estaba confirmada y se cancela, liberar reservas
    elif estado_nuevo in ["cancelado", "anulado"] and estado_viejo == "confirmado":
        remito_insumos = MovimientoStock.objects.filter(
            numero=f"RES-{instance.numero}"
        ).first()
        if remito_insumos:
            remito_insumos.estado = "cancelado"
            remito_insumos.save()
            for linea in remito_insumos.lineas.filter(estado="reservado"):
                linea.estado = "cancelado"
                linea.save()


# -------------------------------------------------------------------------
# 4. LOG AUDITABLE DE CAMBIOS EN ETAPAS DE TALLERISTAS
# -------------------------------------------------------------------------
@receiver(pre_save, sender=OPEtapaTracking)
def capturar_estado_etapa(sender, instance, **kwargs):
    if instance.pk:
        old = OPEtapaTracking.objects.filter(pk=instance.pk).values("estado").first()
        instance._old_estado = old["estado"] if old else None
    else:
        instance._old_estado = None


@receiver(post_save, sender=OPEtapaTracking)
def registrar_log_etapa(sender, instance, created, **kwargs):
    estado_viejo = getattr(instance, "_old_estado", None)
    estado_nuevo = instance.estado

    if created or estado_viejo != estado_nuevo:
        OPEtapaLog.objects.create(
            etapa_tracking=instance,
            usuario=instance.responsable_interno,
            estado_anterior=estado_viejo or "creada",
            estado_nuevo=estado_nuevo,
            observacion=f"Cambio automático de estado a {instance.get_estado_display()}",
        )
