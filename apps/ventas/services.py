from django.db import transaction
from django.utils import timezone
from decimal import Decimal
from django.contrib.contenttypes.models import ContentType
from .models import OrdenVenta, CanalVenta, LineaOrdenVenta, LineaRecargoOrden
from apps.inventario.models import MovimientoStock, LineaMovimientoStock, Ubicacion, Producto
from apps.inventario.services import StockService
from apps.contactos.models import Contacto
from apps.contactos.services import ContactosService
from apps.ventas.dtos import OrdenVentaDTO


class VentasService:
    @classmethod
    @transaction.atomic
    def ingestar_orden_canal(cls, canal, orden_dto: OrdenVentaDTO) -> OrdenVenta:
        """
        Punto de entrada universal y agnóstico de canal para la creación o actualización
        de una Orden de Venta en el ERP a partir de un OrdenVentaDTO.
        """
        # 1. Sincronizar o crear Cliente en Contactos
        cliente = ContactosService.sincronizar_cliente_desde_dto(orden_dto.cliente)

        # 2. Mapear estado externo a estado canónico ERP
        estado_ext = (orden_dto.estado_canal_externo or "").lower()
        if estado_ext in ["processing", "completed", "paid", "confirmed"]:
            estado_erp = "confirmado"
        elif estado_ext in ["cancelled", "failed", "refunded"]:
            estado_erp = "cancelado"
        else:
            estado_erp = "borrador"

        # 3. Upsert OrdenVenta
        prefijo = canal.codigo if canal else "OV"
        numero_orden = f"{prefijo}-{orden_dto.numero_externo or orden_dto.referencia_externa}"

        orden, created = OrdenVenta.objects.update_or_create(
            canal=canal,
            referencia_externa=orden_dto.referencia_externa,
            defaults={
                "numero": numero_orden,
                "numero_externo": orden_dto.numero_externo,
                "estado_canal_externo": orden_dto.estado_canal_externo,
                "estado": estado_erp,
                "cliente": cliente,
                "monto_total": orden_dto.monto_total,
                "total_descuentos": orden_dto.total_descuentos,
                "total_envio": orden_dto.total_envio,
                "total_impuestos": orden_dto.total_impuestos,
                "metodo_envio_titulo": orden_dto.metodo_envio_titulo,
                "metodo_envio_id": orden_dto.metodo_envio_id,
                "metodo_pago": orden_dto.metodo_pago,
                "transaccion_id": orden_dto.transaccion_id,
                "cupones_aplicados": [{"code": c.codigo, "discount": str(c.monto_descuento)} for c in orden_dto.cupones],
                "datos_adicionales_meta": orden_dto.datos_adicionales_meta,
                "fecha": timezone.now().date(),
            }
        )

        # 4. Procesar Recargos / Fees
        orden.recargos.all().delete()
        total_fees = Decimal("0.00")
        for rec in orden_dto.recargos:
            total_fees += rec.monto
            LineaRecargoOrden.objects.create(
                orden=orden,
                nombre=rec.nombre,
                monto=rec.monto,
                impuesto=rec.impuesto,
            )
        orden.total_recargos_fees = total_fees
        orden.save(update_fields=["total_recargos_fees"])

        # 5. Procesar Líneas de Productos
        orden.lineas.all().delete()
        for item in orden_dto.lineas:
            producto = Producto.objects.filter(sku=item.sku).first()
            if not producto:
                continue

            LineaOrdenVenta.objects.create(
                orden=orden,
                producto=producto,
                referencia_linea_externa=item.id_linea_externo,
                cantidad=item.cantidad,
                precio_unitario=item.precio_unitario,
                descuento=item.descuento,
            )

        # 6. Si la orden está confirmada y recién creada, generar remito de entrega y reservar stock
        if estado_erp == "confirmado" and created:
            cls.generar_remito_salida(orden)

        return orden

    @staticmethod
    @transaction.atomic
    def procesar_orden_woocommerce(tienda_id, payload):
        """
        Adaptador de compatibilidad para la ingesta de órdenes WooCommerce.
        Utiliza WooCommerceNormalizer y delega a la API canónica ingestar_orden_canal.
        """
        from apps.integraciones.woocommerce.models import TiendaWooCommerce
        from apps.integraciones.woocommerce.normalizers import WooCommerceNormalizer

        tienda = TiendaWooCommerce.objects.filter(id=tienda_id).select_related("canal_venta").first()
        canal = tienda.canal_venta if tienda else None
        if not canal and tienda:
            # Fallback: asegurar canal para la tienda
            canal, _ = CanalVenta.objects.get_or_create(
                codigo=tienda.codigo_prefijo,
                defaults={
                    "nombre": tienda.nombre,
                    "tipo": "woocommerce",
                    "empresa": tienda.empresa,
                }
            )
            tienda.canal_venta = canal
            tienda.save(update_fields=["canal_venta"])

        orden_dto = WooCommerceNormalizer.normalizar_orden(payload)
        return VentasService.ingestar_orden_canal(canal, orden_dto)

    @staticmethod
    def generar_remito_salida(orden):
        ct = ContentType.objects.get_for_model(orden)

        # Origen: Almacén predeterminado del canal, o almacén principal si no está configurado
        almacen_origen = None
        if orden.canal and orden.canal.almacen_predeterminado:
            almacen_origen = orden.canal.almacen_predeterminado

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
                "observaciones": f"Envío por {orden.metodo_envio_titulo or 'Logística'}",
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
                estado="borrador",
            )
            StockService.reservar_linea(lms)

        return remito

    @staticmethod
    @transaction.atomic
    def eliminar_orden_woocommerce(tienda_id, payload):
        wc_id = str(payload.get("id"))
        from apps.integraciones.woocommerce.models import TiendaWooCommerce
        tienda = TiendaWooCommerce.objects.filter(id=tienda_id).first()
        canal = tienda.canal_venta if tienda else None

        qs = OrdenVenta.objects.filter(referencia_externa=wc_id)
        if canal:
            qs = qs.filter(canal=canal)
        orden = qs.first()

        if orden:
            orden.estado = "cancelado"
            orden.save(update_fields=["estado"])

            # Cancelar reservas de stock si existía remito
            ct = ContentType.objects.get_for_model(orden)
            remitos = MovimientoStock.objects.filter(content_type_origen=ct, object_id_origen=orden.id)
            for remito in remitos:
                for linea_mov in remito.lineas.all():
                    StockService.cancelar_linea(linea_mov)
                remito.estado = "cancelado"
                remito.save(update_fields=["estado"])

    @staticmethod
    @transaction.atomic
    def procesar_producto_woocommerce(tienda_id, payload):
        """Sincroniza el CRUD de Productos desde Woo hacia el ERP."""
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
        # Guardar en un modelo Promocion/Cupón si es necesario para el motor de ventas del ERP.
        pass

    @staticmethod
    @transaction.atomic
    def generar_factura_desde_orden(orden, diario=None):
        """
        Genera un DocumentoDeuda (Factura de Venta) en estado borrador a partir de una OrdenVenta.
        - Mapea cliente y determina el tipo de comprobante AFIP adecuado (A o B).
        - Desglosa líneas de productos, asigna impuestos según el producto o el estándar del 21%.
        - Mapea descuentos globales (`total_descuentos` / cupones) en `monto_descuentos`.
        - Mapea recargos de pasarelas de pago (`fee_lines` / `LineaRecargoOrden`) en `monto_recargos`.
        - Si la empresa es agente de percepción de IIBB/IVA y el cliente califica, calcula y crea TributoDocumentoDeuda.
        """
        from apps.base.models import ConfiguracionEmpresa
        from apps.contabilidad.models import (
            DocumentoDeuda,
            LineaDocumentoDeuda,
            TipoComprobanteAFIP,
            Diario,
            Impuesto,
            TributoDocumentoDeuda,
        )

        empresa = ConfiguracionEmpresa.get_solo()

        # Determinar Diario de Ventas
        if not diario:
            diario = Diario.objects.filter(tipo="ventas").first()
            if not diario:
                diario, _ = Diario.objects.get_or_create(
                    codigo="VEN-WEB",
                    defaults={"nombre": "Ventas Online", "tipo": "ventas", "es_facturacion_electronica": True, "punto_venta_afip": 1}
                )

        # Determinar letra de comprobante según condiciones fiscales
        cond_emisor = getattr(empresa, "condicion_iva", "responsable_inscripto")
        cond_receptor = getattr(orden.cliente, "condicion_iva", "consumidor_final")

        letra = "B"
        if cond_emisor == "monotributista" or cond_emisor == "exento":
            letra = "C"
        elif cond_emisor == "responsable_inscripto":
            if cond_receptor == "responsable_inscripto":
                letra = "A"
            else:
                letra = "B"

        tipo_afip = TipoComprobanteAFIP.objects.filter(
            clasificacion_interna="factura",
            letra=letra,
        ).first()

        numero_factura = f"{diario.codigo}-{orden.numero}"

        # Atribución provincial y de Convenio Multilateral (SIFERE)
        provincia_destino = getattr(orden.cliente, "provincia", "") or ""
        from apps.contabilidad.reports.convenio_multilateral_report import NOMBRE_PROVINCIA_A_CODIGO_SIFERE
        jurisdiccion_sifere = NOMBRE_PROVINCIA_A_CODIGO_SIFERE.get(provincia_destino.strip().lower(), "902") if provincia_destino else "902"

        # Crear cabecera DocumentoDeuda
        factura = DocumentoDeuda.objects.create(
            numero=numero_factura,
            diario=diario,
            tipo="factura_cliente",
            tipo_comprobante_afip=tipo_afip,
            contacto=orden.cliente,
            fecha_emision=timezone.now().date(),
            orden_venta=orden,
            estado="borrador",
            monto_descuentos=orden.total_descuentos,
            monto_recargos=orden.total_recargos_fees + orden.total_envio,
            provincia_destino=provincia_destino,
            jurisdiccion_sifere=jurisdiccion_sifere,
        )

        # Buscar impuesto IVA por defecto (21%)
        impuesto_iva_21 = Impuesto.objects.filter(tipo="iva", alicuota=Decimal("21.00")).first()

        neto_acumulado = Decimal("0.00")
        iva_acumulado = Decimal("0.00")

        # 1. Crear líneas de productos
        for linea_orden in orden.lineas.all():
            imp = getattr(linea_orden.producto, "impuesto", None) or impuesto_iva_21
            subtotal_linea = linea_orden.cantidad * linea_orden.precio_unitario

            LineaDocumentoDeuda.objects.create(
                documento=factura,
                producto=linea_orden.producto,
                descripcion=f"{linea_orden.producto.sku} - {linea_orden.producto.nombre}",
                cantidad=linea_orden.cantidad,
                precio_unitario=linea_orden.precio_unitario,
                impuesto=imp,
                subtotal=subtotal_linea,
            )
            neto_acumulado += subtotal_linea
            if imp and imp.alicuota > 0:
                iva_acumulado += (subtotal_linea * imp.alicuota) / Decimal("100.00")

        # 2. Agregar conceptos por recargos o costos de envío si existen
        if orden.total_envio > 0:
            LineaDocumentoDeuda.objects.create(
                documento=factura,
                descripcion=f"Envío a domicilio ({orden.metodo_envio_titulo or 'Logística'})",
                cantidad=Decimal("1.00"),
                precio_unitario=orden.total_envio,
                impuesto=impuesto_iva_21,
                subtotal=orden.total_envio,
            )
            neto_acumulado += orden.total_envio
            if impuesto_iva_21:
                iva_acumulado += (orden.total_envio * impuesto_iva_21.alicuota) / Decimal("100.00")

        for recargo in orden.recargos.all():
            LineaDocumentoDeuda.objects.create(
                documento=factura,
                descripcion=f"Recargo: {recargo.nombre}",
                cantidad=Decimal("1.00"),
                precio_unitario=recargo.monto,
                impuesto=impuesto_iva_21,
                subtotal=recargo.monto,
            )
            neto_acumulado += recargo.monto
            if impuesto_iva_21:
                iva_acumulado += (recargo.monto * impuesto_iva_21.alicuota) / Decimal("100.00")

        # Deducción de descuentos del neto gravado global
        neto_final = max(Decimal("0.00"), neto_acumulado - orden.total_descuentos)

        # 3. Tratamiento de Percepciones si la empresa es agente fiscal
        monto_tributos_acum = Decimal("0.00")
        if empresa.es_agente_percepcion_iibb and cond_receptor == "responsable_inscripto":
            alicuota_percep = Decimal("3.00")  # Alícuota padrón ARBA/AGIP
            imp_percep = Impuesto.objects.filter(tipo="percepcion_iibb").first()
            monto_percep = (neto_final * alicuota_percep) / Decimal("100.00")

            TributoDocumentoDeuda.objects.create(
                documento=factura,
                afip_tributo_id=2,  # IIBB
                descripcion=f"Percepción IIBB ({alicuota_percep}%)",
                base_imponible=neto_final,
                alicuota=alicuota_percep,
                importe=monto_percep,
                impuesto=imp_percep,
            )
            monto_tributos_acum += monto_percep

        factura.monto_neto = neto_final
        factura.monto_impuestos = iva_acumulado
        factura.monto_tributos = monto_tributos_acum
        factura.monto_total = neto_final + iva_acumulado + monto_tributos_acum
        factura.save(update_fields=["monto_neto", "monto_impuestos", "monto_tributos", "monto_total"])

        return factura


