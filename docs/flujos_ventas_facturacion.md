# Módulo de Ventas y Facturación

> 🧭 **Navegación**: [Índice General](README.md) ➔ Anterior: [Flujos de Compras](flujos_compras.md) ➔ **Flujos de Ventas** ➔ Siguiente: [Flujos de Tesorería](flujos_tesoreria.md)

Este documento detalla la lógica comercial del sistema Indino, abarcando la captura de pedidos y la emisión de comprobantes (fiscales y no fiscales).

## 1. Captura de Pedidos (Omnicanalidad)

Los clientes se administran centralizadamente en `contactos.Contacto` (`tipo='cliente'`), discriminando entre cliente final y distribuidor con su condición impositiva y límite de crédito.

### A. Venta Minorista (B2C)
- **Origen principal**: Sincronización automática vía Webhooks desde WooCommerce o ventas de mostrador / POS.
- **Condición de Pago**: 100% al contado o pasarela de pago (MercadoPago / tarjetas).
- **Flujo de Stock**: Genera un `MovimientoStock` de tipo `entrega` en estado `finalizado` que descuenta del Quant físico en depósito central hacia la ubicación virtual "Clientes".

### B. Venta Mayorista / Distribuidores (B2B - Make to Order)
- **Origen**: Carga en panel administrativo mediante `PedidoVenta` (hereda de `DocumentoBase`).
- **Condición de Pago**: Pago diferido. Requiere una Seña (ej. 30% a 50%) para confirmar la producción.
- **Flujo Operativo**:
  1. El `PedidoVenta` se crea en estado `borrador`.
  2. Tesorería imputa el cobro de la seña en `MovimientoCaja`.
  3. El pedido pasa a `confirmado`, disparando la creación automática de una `OrdenProduccion` con las variantes y curva de talles requeridas.
  4. Al finalizar la OP (productos ingresados al depósito), se notifica la disponibilidad, se emite el comprobante por el saldo (contraentrega) y se genera el `MovimientoStock` de entrega.

## 2. Facturación y Comprobantes (Dualidad)

- **Facturación Oficial (AFIP)**: Emisión de comprobantes electrónicos vinculados al CUIT y condición frente al IVA del `Contacto`. Impacta en las Cajas Oficiales de Tesorería.
- **Comprobantes Internos (Remitos / Documentos X)**: Registro de control logístico interno.
- **Archivos Adjuntos**: Mediante `DocumentoAdjunto`, cada pedido o remito puede almacenar copias de órdenes de compra del cliente, remitos firmados con sello de recepción o comprobantes de transferencia.

## 3. Cuentas Corrientes y Límite de Crédito
- El saldo se actualiza por débitos (entregas) y créditos (cobros).
- Si el saldo deudor supera el `limite_credito` configurado en el `Contacto`, el sistema bloquea la confirmación de nuevos despachos hasta regularizar la cuenta.

