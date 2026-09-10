from django.db import transaction
from django.utils import timezone
from decimal import Decimal
from django.contrib.contenttypes.models import ContentType
from .models import OrdenVenta, TiendaWooCommerce, LineaOrdenVenta, LineaRecargoOrden
from apps.inventario.models import MovimientoStock, LineaMovimientoStock, Ubicacion
from apps.inventario.services import StockService
from apps.contactos.models import Contacto

class VentasService:
    @staticmethod
    @transaction.atomic
    def procesar_orden_woocommerce(tienda_id, payload):
        """
        Recibe el payload limpio del webhook o polling y genera/actualiza la OrdenVenta.
        """
        tienda = TiendaWooCommerce.objects.get(id=tienda_id)
        wc_id = payload.get("id")
        
        # 1. Buscar o Crear Cliente
        billing = payload.get("billing", {})
        email = billing.get("email")
        cuit = None
        
        # Buscar CUIT/DNI en metadatos
        for meta in payload.get("meta_data", []):
            if meta.get("key") in ["_billing_cuit", "_billing_dni"]:
                cuit = meta.get("value")
                break
                
        cliente = Contacto.objects.filter(email=email).first()
        if not cliente and cuit:
            cliente = Contacto.objects.filter(numero_documento=cuit).first()
            
        if not cliente:
            cliente = Contacto.objects.create(
                nombre=f"{billing.get('first_name', '')} {billing.get('last_name', '')}".strip(),
                email=email,
                telefono=billing.get("phone", ""),
                direccion=f"{billing.get('address_1', '')}, {billing.get('city', '')}",
                numero_documento=cuit or "",
                tipo_documento="CUIT" if cuit and len(str(cuit)) > 8 else "DNI",
                es_cliente=True
            )

        # 2. Upsert OrdenVenta
        estado_wc = payload.get("status", "")
        estado_erp = "confirmado" if estado_wc in ["processing", "completed"] else "borrador"
        if estado_wc in ["cancelled", "failed", "refunded"]:
            estado_erp = "cancelado"

        orden, created = OrdenVenta.objects.update_or_create(
            tienda=tienda,
            wc_order_id=wc_id,
            defaults={
                "numero": f"{tienda.codigo_prefijo}-{payload.get('number', wc_id)}",
                "wc_order_number": str(payload.get("number", "")),
                "wc_status": estado_wc,
                "estado": estado_erp,
                "cliente": cliente,
                "monto_total": Decimal(payload.get("total", "0.0")),
                "total_descuentos": Decimal(payload.get("discount_total", "0.0")),
                "total_envio": Decimal(payload.get("shipping_total", "0.0")),
                "total_impuestos": Decimal(payload.get("total_tax", "0.0")),
                "metodo_pago": payload.get("payment_method_title", ""),
                "transaccion_id": payload.get("transaction_id", ""),
                "fecha": timezone.now().date(), # Idealmente parsear date_created_gmt
            }
        )

        # 3. Procesar Líneas de Envío
        shipping_lines = payload.get("shipping_lines", [])
        if shipping_lines:
            orden.metodo_envio_titulo = shipping_lines[0].get("method_title", "")
            orden.metodo_envio_id = shipping_lines[0].get("method_id", "")
            orden.save(update_fields=["metodo_envio_titulo", "metodo_envio_id"])

        # 4. Procesar Cupones
        coupon_lines = payload.get("coupon_lines", [])
        if coupon_lines:
            orden.cupones_aplicados = [{"code": c.get("code"), "discount": c.get("discount")} for c in coupon_lines]
            orden.save(update_fields=["cupones_aplicados"])

        # 5. Procesar Fees (Recargos)
        orden.recargos.all().delete() # Limpieza por si es un update
        total_fees = Decimal("0.0")
        for fee in payload.get("fee_lines", []):
            monto_fee = Decimal(fee.get("total", "0.0"))
            total_fees += monto_fee
            LineaRecargoOrden.objects.create(
                orden=orden,
                nombre=fee.get("name", "Recargo"),
                monto=monto_fee,
                impuesto=Decimal(fee.get("total_tax", "0.0"))
            )
        orden.total_recargos_fees = total_fees
        orden.save(update_fields=["total_recargos_fees"])

        # 6. Procesar Line Items (Productos)
        from apps.inventario.models import Producto
        
        orden.lineas.all().delete()
        for item in payload.get("line_items", []):
            sku = item.get("sku")
            producto = Producto.objects.filter(sku=sku).first()
            if not producto:
                # TODO: Lógica de creación de producto on-the-fly o marcar como error
                continue
                
            LineaOrdenVenta.objects.create(
                orden=orden,
                producto=producto,
                wc_line_id=item.get("id"),
                cantidad=Decimal(str(item.get("quantity", 0))),
                precio_unitario=Decimal(item.get("price", "0.0")),
                descuento=Decimal("0.0") # El descuento ya suele venir en el subtotal
            )

        # 7. Si está confirmada, generar remito de salida
        if estado_erp == "confirmado" and created:
            VentasService.generar_remito_salida(orden)

        return orden

    @staticmethod
    def generar_remito_salida(orden):
        ct = ContentType.objects.get_for_model(orden)
        
        # Origen: Almacén de la tienda, o almacén principal si no está configurado
        almacen_origen = orden.tienda.almacen_origen
        if not almacen_origen:
            almacen_origen, _ = Ubicacion.objects.get_or_create(tipo="interna", nombre="Almacén Principal")
            
        ubicacion_cliente, _ = Ubicacion.objects.get_or_create(tipo="cliente", nombre="Ubicación Cliente")

        remito, _ = MovimientoStock.objects.get_or_create(
            numero=f"REM-OV-{orden.id}",
            defaults={
                "tipo": "entrega",
                "estado": "confirmado",
                "ubicacion_origen": almacen_origen,
                "ubicacion_destino": ubicacion_cliente,
                "contacto": orden.cliente,
                "content_type_origen": ct,
                "object_id_origen": orden.id,
                "documento_origen": orden.numero,
                "observaciones": f"Envío por {orden.metodo_envio_titulo}",
            }
        )
        
        for linea in orden.lineas.all():
            lms = LineaMovimientoStock.objects.create(
                movimiento=remito,
                producto=linea.producto,
                cantidad=linea.cantidad,
                cantidad_hecha=linea.cantidad,
                ubicacion_origen=almacen_origen,
                ubicacion_destino=ubicacion_cliente,
                estado="borrador"
            )
            StockService.reservar_linea(lms)
            
        return remito

    @staticmethod
    @transaction.atomic
    def eliminar_orden_woocommerce(tienda_id, payload):
        wc_id = payload.get("id")
        orden = OrdenVenta.objects.filter(tienda_id=tienda_id, wc_order_id=wc_id).first()
        if orden:
            # En un ERP rara vez se elimina físicamente una orden; se cancela.
            orden.estado = "cancelado"
            orden.save(update_fields=["estado"])
            
            # TODO: Cancelar reservas de stock usando StockService

    @staticmethod
    @transaction.atomic
    def procesar_producto_woocommerce(tienda_id, payload):
        """Sincroniza el CRUD de Productos desde Woo hacia el ERP."""
        from apps.inventario.models import Producto
        sku = payload.get("sku")
        if not sku:
            return # Sin SKU no podemos cruzar la base de datos de manera fiable
            
        producto, created = Producto.objects.update_or_create(
            sku=sku,
            defaults={
                "nombre": payload.get("name", ""),
                "descripcion": payload.get("short_description", "") or payload.get("description", ""),
                "precio_venta": Decimal(payload.get("regular_price") or payload.get("price") or "0.0"),
                "activo": payload.get("status") == "publish",
            }
        )
        
        # Opcional: Procesar categorías y atributos (variaciones)
        
    @staticmethod
    @transaction.atomic
    def eliminar_producto_woocommerce(tienda_id, payload):
        from apps.inventario.models import Producto
        sku = payload.get("sku")
        if sku:
            # En ERP no borramos, inactivamos.
            Producto.objects.filter(sku=sku).update(activo=False)

    @staticmethod
    @transaction.atomic
    def procesar_cupon_woocommerce(tienda_id, payload):
        """
        Sincroniza la definición de cupones. 
        Nota: Esto puede guardarse en un modelo promocional si el ERP lo maneja.
        Por ahora solo guardamos logs o definimos una estructura base.
        """
        codigo = payload.get("code")
        tipo_descuento = payload.get("discount_type")
        monto = payload.get("amount")
        # TODO: Guardar en un modelo Promocion/Cupón si es necesario para el motor de ventas del ERP.
        pass

