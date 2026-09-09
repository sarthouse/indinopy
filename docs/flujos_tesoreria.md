# Módulo de Tesorería (Flujos de Caja)

> 🧭 **Navegación**: [Índice General](README.md) ➔ Anterior: [Flujos de Ventas](flujos_ventas_facturacion.md) ➔ **Flujos de Tesorería** ➔ Siguiente: [Guía Rápida Operativa](manuales/guia_rapida_operativa.md)

El módulo de Tesorería es el corazón financiero de Indino. Controla el dinero que entra, el que sale, y dónde está guardado físicamente o digitalmente.

## 1. Gestión de Cajas y Cuentas Bancarias

Para soportar la dualidad fiscal y operativa, el sistema maneja múltiples "Cajas":
- **Cajas Oficiales**: Cuentas bancarias, pasarelas digitales (MercadoPago) y Caja Chica oficial.
- **Cajas Extraoficiales**: Cajas operativas de planta para transacciones internas y anticipos en efectivo.

## 2. Flujo de Ingresos (Cobranzas)

Todo ingreso genera un documento de cobro (`DocumentoBase`):
- **Señas de Distribuidores**: Pago adelantado que habilita la confirmación de la OP.
- **Cobro de Saldos**: Contraentrega de mercadería mayorista.
- **Ventas Minoristas**: Liquidaciones de cobranza digital.
- **Comprobantes Adjuntos**: Permite adjuntar el comprobante de transferencia bancaria o ticket de depósito mediante `DocumentoAdjunto`.

## 3. Flujo de Egresos (Pagos)

Los egresos se documentan mediante órdenes de pago con asignación de caja:

### A. Pago a Proveedores (Compras)
- Originados en comprobantes de compra ingresados tras la recepción de mercadería.
- Posibilidad de imputar pagos parciales o diferidos contra el saldo de `contactos.Contacto`.

### B. Liquidación a Talleristas (Servicios de Producción)
- **Cálculo Automático por Etapa**: Cada `OPEtapa` finalizada en una OP registra al tallerista (`contactos.Contacto`) y su `costo_real`.
- **Panel de Liquidación**: Tesorería agrupa semanalmente todas las tareas completadas por el mismo tallerista a través de múltiples OPs.
- **Emisión de Pago**: Se genera la liquidación, se debita de la caja seleccionada y se puede adjuntar el recibo firmado por el tallerista.

## 4. Gestión de Cheques y Valores en Cartera
- Trazabilidad de cheques propios y de terceros (emisor, banco, CUIT, fecha de cobro y estado: en cartera, depositado, rechazado o endosado a proveedor).
- Todos los montos se operan bajo el estándar `DecimalField(max_digits=15, decimal_places=2)`.

