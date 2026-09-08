# Módulo de Tesorería (Flujos de Caja)

El módulo de Tesorería es el corazón financiero de Indino. Controla el dinero que entra, el que sale, y dónde está guardado físicamente o digitalmente.

## 1. Gestión de Cajas y Cuentas Bancarias

Para soportar la dualidad fiscal y operativa, el sistema maneja múltiples "Cajas":
- **Cajas Oficiales**: Cuentas bancarias, MercadoPago, y Caja Chica (Fondo Fijo) facturada.
- **Cajas Extraoficiales**: Billeteras o cajas fuertes internas para transacciones con comprobantes "X".

Las transferencias entre cajas y las conciliaciones bancarias son funcionalidades clave de este módulo.

## 2. Flujo de Ingresos (Cobranzas)

Todo dinero que entra a la empresa genera un **Recibo**:
- **Señas de Distribuidores**: Pago adelantado que habilita la creación de la OP.
- **Cobro de Saldos**: Pago contraentrega de pedidos mayoristas.
- **Ventas Minoristas**: Liquidación diaria de MercadoPago o WooCommerce.

## 3. Flujo de Egresos (Pagos)

Todo dinero que sale de la empresa genera una **Orden de Pago**. Existen dos grandes grupos de egresos:

### A. Pago a Proveedores (Compras)
- Nacen de las Facturas de Compra cargadas en el módulo de Compras.
- Se pueden pagar al contado o registrar pagos diferidos (ej. entrega de cheques de terceros o propios).

### B. Liquidación a Talleristas (Servicios de Producción)
Este es el egreso más crítico de Indino.
1. Cuando Producción avanza una OP y marca una etapa como completada (ej. "Aparado de 100 pares terminado por Juan"), el sistema calcula automáticamente la deuda: `100 pares x $Costo Unitario = $Deuda a Juan`.
2. Tesorería tiene un panel de "Liquidación de Talleristas" donde agrupa todas las etapas sueltas que hizo "Juan" en la semana para múltiples OPs.
3. Se emite la Orden de Pago y se debita de la Caja correspondiente.

## 4. Gestión de Cheques (Valores en Cartera)
Registro de cheques recibidos de clientes (Valores a Depositar) que pueden ser depositados en el banco, o endosados y entregados a proveedores de insumos (una práctica muy común en la manufactura argentina).

