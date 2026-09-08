# Módulo de Ventas y Facturación

Este documento detalla la lógica comercial del sistema Indino, abarcando la captura de pedidos y la emisión de comprobantes (fiscales y no fiscales).

## 1. Captura de Pedidos (Omnicanalidad)

El sistema soporta dos flujos principales dependiendo del tipo de cliente:

### A. Venta Minorista (B2C)
- **Origen principal**: Sincronización automática vía Webhooks desde WooCommerce o ventas manuales en mostrador (POS).
- **Condición de Pago**: 100% al contado o mediante pasarela de pago (MercadoPago, Tarjetas).
- **Flujo de Stock**: Descuenta inmediatamente del "Stock Disponible" en Almacén. Si no hay stock, no se puede vender (o entra como *Backorder*).

### B. Venta Mayorista / Distribuidores (B2B)
- **Origen**: Carga manual por parte de un vendedor en el panel de Django, o un portal B2B específico.
- **Condición de Pago**: Pago diferido. Requiere el ingreso de una **Seña** (ej. 30% o 50%) para confirmar el pedido.
- **Flujo Operativo**: 
  1. El pedido entra en estado `Esperando Seña`.
  2. Tesorería imputa el pago de la seña.
  3. El sistema genera automáticamente una **Orden de Producción (OP)** para fabricar el lote.
  4. Al finalizar la OP, el sistema avisa al cliente. Se abona el saldo restante (Contraentrega) y se despacha.

## 2. Facturación y Comprobantes (Dualidad)

La realidad industrial muchas veces requiere un manejo dual de la facturación. El sistema emitirá comprobantes desde el módulo de Ventas:

- **Comprobante Fiscal (Factura A/B/C)**: Integración con los webservices de AFIP para emitir facturas electrónicas oficiales. Estos comprobantes impactan en la "Caja Oficial" de Tesorería.
- **Comprobante Interno (Comprobante X / Remito)**: Documento de validez estrictamente interna para el control de entrega y cobro de saldo no fiscalizado. Impacta en la "Caja Extraoficial" de Tesorería.

## 3. Cuentas Corrientes de Clientes
El sistema mantendrá un saldo por cliente.
- **Cargos (Debe)**: Cada vez que se le entrega mercadería (Factura o Comprobante X).
- **Abonos (Haber)**: Cada vez que ingresa un pago (Recibo).
- Esto permite a los Distribuidores operar con saldo a favor o deudas controladas por un límite de crédito.

