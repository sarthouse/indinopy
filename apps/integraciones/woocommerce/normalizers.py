from decimal import Decimal
from typing import Optional
from apps.ventas.dtos import (
    OrdenVentaDTO,
    ClienteDTO,
    LineaOrdenDTO,
    RecargoDTO,
    CuponDTO,
)


class WooCommerceNormalizer:
    """
    Normalizador que traduce payloads crudos de la API REST v3 y Webhooks de WooCommerce
    hacia objetos DTO canónicos agnósticos para el ERP.
    """

    @staticmethod
    def normalizar_cliente(payload_billing: dict, meta_data: Optional[list] = None) -> ClienteDTO:
        meta_data = meta_data or []
        cuit = None

        # 1. Extraer CUIT/DNI desde metadatos estándar de WooCommerce Argentina
        for meta in meta_data:
            key = meta.get("key", "")
            if key in ["_billing_cuit", "_billing_dni", "billing_dni", "billing_cuit", "cuit", "dni"]:
                cuit = str(meta.get("value", "")).strip()
                break

        nombre = f"{payload_billing.get('first_name', '')} {payload_billing.get('last_name', '')}".strip()
        if not nombre:
            nombre = payload_billing.get("company", "") or "Cliente Web"

        direccion = f"{payload_billing.get('address_1', '')} {payload_billing.get('address_2', '')}".strip()

        # Condición frente al IVA
        condicion_iva = "consumidor_final"
        for meta in meta_data:
            if meta.get("key") in ["_billing_condicion_iva", "condicion_iva"]:
                condicion_iva = str(meta.get("value", "")).strip().lower()
                break

        return ClienteDTO(
            nombre=nombre,
            email=payload_billing.get("email", ""),
            cuit=cuit or None,
            telefono=payload_billing.get("phone", ""),
            direccion=direccion,
            ciudad=payload_billing.get("city", ""),
            provincia=payload_billing.get("state", ""),
            codigo_postal=payload_billing.get("postcode", ""),
            condicion_iva=condicion_iva,
        )

    @classmethod
    def normalizar_orden(cls, payload: dict) -> OrdenVentaDTO:
        """
        Traduce un payload de orden de WooCommerce (vía Webhook o GET /orders) a un OrdenVentaDTO.
        """
        wc_id = str(payload.get("id"))
        numero_externo = str(payload.get("number", wc_id))
        estado_wc = payload.get("status", "")

        billing = payload.get("billing", {})
        meta_data = payload.get("meta_data", [])
        cliente_dto = cls.normalizar_cliente(billing, meta_data)

        # 1. Líneas de productos (line_items)
        lineas = []
        for item in payload.get("line_items", []):
            sku = (item.get("sku") or "").strip()
            lineas.append(
                LineaOrdenDTO(
                    sku=sku,
                    cantidad=Decimal(str(item.get("quantity", 0))),
                    precio_unitario=Decimal(str(item.get("price", "0.0"))),
                    descuento=Decimal("0.00"),
                    nombre_producto=item.get("name", ""),
                    id_linea_externo=str(item.get("id", "")),
                )
            )

        # 2. Recargos y comisiones de pasarela (fee_lines)
        recargos = []
        for fee in payload.get("fee_lines", []):
            recargos.append(
                RecargoDTO(
                    nombre=fee.get("name", "Recargo"),
                    monto=Decimal(str(fee.get("total", "0.0"))),
                    impuesto=Decimal(str(fee.get("total_tax", "0.0"))),
                )
            )

        # 3. Cupones de descuento (coupon_lines)
        cupones = []
        for c in payload.get("coupon_lines", []):
            cupones.append(
                CuponDTO(
                    codigo=c.get("code", ""),
                    monto_descuento=Decimal(str(c.get("discount", "0.0"))),
                )
            )

        # 4. Datos logísticos
        shipping_lines = payload.get("shipping_lines", [])
        metodo_envio_titulo = shipping_lines[0].get("method_title", "") if shipping_lines else ""
        metodo_envio_id = shipping_lines[0].get("method_id", "") if shipping_lines else ""

        return OrdenVentaDTO(
            referencia_externa=wc_id,
            numero_externo=numero_externo,
            estado_canal_externo=estado_wc,
            cliente=cliente_dto,
            lineas=lineas,
            recargos=recargos,
            cupones=cupones,
            monto_total=Decimal(str(payload.get("total", "0.0"))),
            total_descuentos=Decimal(str(payload.get("discount_total", "0.0"))),
            total_envio=Decimal(str(payload.get("shipping_total", "0.0"))),
            total_impuestos=Decimal(str(payload.get("total_tax", "0.0"))),
            metodo_envio_titulo=metodo_envio_titulo,
            metodo_envio_id=metodo_envio_id,
            metodo_pago=payload.get("payment_method_title", ""),
            transaccion_id=payload.get("transaction_id", ""),
            datos_adicionales_meta={"meta_data": meta_data, "raw_status": estado_wc},
        )
