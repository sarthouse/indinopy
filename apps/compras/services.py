from decimal import Decimal
import uuid
from datetime import date
from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError

from apps.compras.models import OrdenCompra, LineaOrdenCompra
from apps.inventario.models import MovimientoStock
from apps.inventario.services import StockService
from apps.base.models import Moneda
from apps.contabilidad.models import CondicionPago, Diario, DocumentoDeuda, LineaDocumentoDeuda, TipoComprobanteAFIP


class ComprasService:
    @staticmethod
    @transaction.atomic
    def confirmar_oc(oc):
        if oc.estado not in ["cotizacion", "borrador"]:
            return
            
        oc.estado = "confirmado"
        oc.save(update_fields=["estado"])
        
        # Genera el remito de recepción en Almacén
        return oc.generar_recepcion_stock()

    @staticmethod
    @transaction.atomic
    def cancelar_oc(oc):
        if oc.estado not in ["cotizacion", "borrador", "confirmado"]:
            return
            
        oc.estado = "cancelado"
        oc.save(update_fields=["estado"])
        
        ct = ContentType.objects.get_for_model(oc)
        remitos_pendientes = MovimientoStock.objects.filter(
            content_type_origen=ct,
            object_id_origen=oc.id,
            tipo="recepcion",
            estado__in=["borrador", "confirmado"],
        )
        for remito in remitos_pendientes:
            remito.estado = "cancelado"
            remito.save(update_fields=["estado"])
            for linea in remito.lineas.filter(estado__in=["borrador", "reservado"]):
                StockService.cancelar_linea(linea)

    @staticmethod
    @transaction.atomic
    def crear_oc_borrador(proveedor, producto, cantidad, ubicacion_destino=None, moneda=None, condicion_pago=None):
        """
        Crea una Orden de Compra en estado borrador generada por el MRP o por reabastecimiento.
        """
        numero_oc = f"OC-MRP-{str(uuid.uuid4())[:6].upper()}"

        if not moneda:
            moneda = Moneda.objects.filter(codigo="ARS").first() or Moneda.objects.first()
            if not moneda:
                moneda = Moneda.objects.create(codigo="ARS", nombre="Pesos Argentinos", simbolo="$")

        if not condicion_pago:
            condicion_pago = CondicionPago.objects.filter(activa=True).first()
            if not condicion_pago:
                condicion_pago = CondicionPago.objects.create(nombre="Contado")

        oc = OrdenCompra.objects.create(
            numero=numero_oc,
            proveedor=proveedor,
            fecha=date.today(),
            estado="borrador",
            moneda=moneda,
            condicion_pago=condicion_pago,
            observaciones="Generado automáticamente por el motor MRP (Regla de Abastecimiento).",
        )

        # Buscar tarifa si existe
        tarifa = None
        if hasattr(producto, "tarifas_proveedores"):
            tarifa = producto.tarifas_proveedores.filter(proveedor=proveedor).first()

        precio = tarifa.precio if tarifa else Decimal("0.0000")

        # Determinar unidad de medida
        um = None
        if hasattr(producto, "template") and producto.template and producto.template.unidad_medida:
            um = producto.template.unidad_medida

        LineaOrdenCompra.objects.create(
            orden_compra=oc,
            producto=producto,
            cantidad=Decimal(str(cantidad)),
            precio_unitario=precio,
            unidad_medida=um,
        )

        return oc

    @staticmethod
    @transaction.atomic
    def crear_factura_proveedor(
        oc: OrdenCompra,
        numero_factura: str,
        fecha_emision: date = None,
        tipo_comprobante_afip: TipoComprobanteAFIP = None,
        basado_en: str = "recibido",
    ) -> DocumentoDeuda:
        """
        Genera la Factura de Compra (DocumentoDeuda) a partir de una Orden de Compra (3-Way Matching).
        basado_en:
          - 'recibido': Factura lo recibido efectivamente en los remitos pendientes de facturar.
          - 'pedido': Factura la totalidad de las cantidades pedidas en la OC.
        """
        if oc.estado not in ["confirmado", "finalizado"]:
            raise ValidationError(f"No se puede facturar una orden de compra en estado {oc.estado}.")

        # Buscar diario de compras
        diario_compras = Diario.objects.filter(tipo="compras").first()
        if not diario_compras:
            diario_compras = Diario.objects.create(
                codigo="COMPRAS",
                nombre="Diario de Compras",
                tipo="compras",
            )

        fecha_emision = fecha_emision or date.today()

        factura = DocumentoDeuda.objects.create(
            numero=numero_factura,
            diario=diario_compras,
            tipo="factura_proveedor",
            tipo_comprobante_afip=tipo_comprobante_afip,
            contacto=oc.proveedor,
            fecha_emision=fecha_emision,
            fecha_vencimiento=oc.fecha_entrega_esperada or fecha_emision,
            condicion_pago=oc.condicion_pago,
            moneda=oc.moneda,
            tasa_cambio=oc.tipo_cambio,
            orden_compra=oc,
            estado="borrador",
        )

        monto_neto = Decimal("0.00")
        monto_iva = Decimal("0.00")

        lineas_a_procesar = []
        for linea in oc.lineas.all():
            if basado_en == "recibido":
                # Facturar lo que se recibió y aún no se facturó
                cant = max(Decimal("0.0000"), linea.cantidad_recibida - linea.cantidad_facturada)
            else:
                cant = max(Decimal("0.0000"), linea.cantidad - linea.cantidad_facturada)

            if cant <= Decimal("0.0000"):
                continue

            subtotal_linea = (cant * linea.precio_unitario).quantize(Decimal("0.01"))
            iva_linea = Decimal("0.00")
            if linea.impuesto:
                iva_linea = (subtotal_linea * (linea.impuesto.alicuota / Decimal("100.00"))).quantize(Decimal("0.01"))

            monto_neto += subtotal_linea
            monto_iva += iva_linea

            LineaDocumentoDeuda.objects.create(
                documento=factura,
                producto=linea.producto,
                descripcion=linea.descripcion or f"{linea.producto.sku} - {linea.producto}",
                cantidad=cant,
                precio_unitario=linea.precio_unitario,
                impuesto=linea.impuesto,
                subtotal=subtotal_linea,
            )

            # Actualizar cantidad facturada en la OC
            linea.cantidad_facturada += cant
            linea.save(update_fields=["cantidad_facturada"])

        if not factura.lineas.exists():
            factura.delete()
            raise ValidationError("No hay cantidades pendientes de facturar para esta orden de compra.")

        factura.monto_neto = monto_neto
        factura.monto_impuestos = monto_iva
        factura.monto_total = monto_neto + monto_iva
        factura.save(update_fields=["monto_neto", "monto_impuestos", "monto_total"])

        return factura
