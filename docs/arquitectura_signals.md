# Arquitectura de Señales y Automatización (Estilo Odoo)

> 🧭 **Navegación**: [Índice General](README.md) ➔ Anterior: [Lógica de Negocio](logica.md) ➔ **Arquitectura de Señales** ➔ Siguiente: [Flujos de Compras](flujos_compras.md) | [Recopilación Integral](recopilacion_sistema.md)

En un ERP moderno como Odoo, los módulos casi no hablan entre sí de forma síncrona manual, sino que reaccionan a eventos. En Django, esto se logra mediante **Signals** (Señales) o llamando a **Servicios** en los cambios de estado.

A continuación, el mapa de las señales críticas que necesitaremos programar para que Indino funcione en "piloto automático":

## 1. Núcleo de Inventario (`apps/inventario/signals.py`)
- **Sembrado inicial de unidades (`post_migrate`)**:
  - `auto_sembrar_unidades_medida`: Al correr migraciones de inventario, si la tabla `UnidadMedida` está vacía, puebla automáticamente unidades estándar del rubro (`u`, `par`, `m`, `cm`, `kg`, `g`, `l`, `hs`, `min`).
- **Control atómico de Quants (`pre_save` y `post_save` en `MovimientoStock`)**:
  - `capturar_estado_anterior_movimiento`: Registra en memoria `_old_estado` antes de guardar.
  - `procesar_movimiento_stock`: Envuelto en `transaction.atomic()`.
    - `confirmado`: Incrementa `cantidad_reservada` en origen.
    - `finalizado`: Si venía de `confirmado`, descuenta `cantidad_reservada`; deduce `cantidad_fisica` en origen e incrementa `cantidad_fisica` en destino. Si los quants llegan a cero físico y reservado, se eliminan para no ensuciar la base.
    - `cancelado`: Si estaba `confirmado`, libera la `cantidad_reservada`.

## 2. Intersección Producción ⟷ Inventario (`apps/produccion/signals.py`)
- **Cálculo de Insumos (`pre_save` OrdenProduccion a 'confirmado')**:
  - `calcular_insumos_requeridos_op`: Itera sobre las `OPVariacion` del lote, evalúa las reglas de `RecetaInsumo.variantes_destino` y crea o consolida los registros en `OPInsumoRequerido` con sus SKUs específicos.
- **Reserva de Materiales (`post_save` OrdenProduccion a 'confirmado')**:
  - `reservar_insumos_op`: Genera un `MovimientoStock` de tipo `produccion` en estado `confirmado` desde el almacén interno hacia la ubicación virtual de producción, bloqueando el stock disponible de los insumos requeridos.
- **Finalización de Fabricación (`post_save` OrdenProduccion a 'finalizado')**:
  - `ejecutar_produccion_op`:
    - Pasa los movimientos de insumos asociados a `finalizado` (consumo físico real).
    - Crea y finaliza un `MovimientoStock` de entrada desde "Producción" hacia "Depósito Central" con las cantidades y variantes de `OPVariacion` producidas.

## 3. Intersección Compras ⟷ Inventario ⟷ Tesorería (Próxima Implementación)
- **Al Confirmar Orden de Compra (`post_save` OrdenCompra a 'confirmado')**:
  - Genera automáticamente un `MovimientoStock` de tipo `recepcion` en estado `borrador` o `confirmado` con origen en la ubicación virtual del `proveedor` y destino en el almacén interno.
- **Al Recibir Mercadería (`MovimientoStock` pasa a 'finalizado')**:
  - Se incrementa el Quant físico en depósito.
  - Se actualiza la cantidad recibida en las líneas de la `OrdenCompra`.
- **Al Cargar Comprobante / Factura del Proveedor**:
  - Se valida contra las cantidades recepcionadas y se genera la Cuenta por Pagar / Orden de Pago en `tesoreria`.

## 4. Intersección Ventas ⟷ Inventario / Producción (Make to Order)
- **Al Confirmar Pedido Minorista (`post_save` PedidoVenta a 'confirmado' / 'pagado')**:
  - Genera un `MovimientoStock` de tipo `entrega` hacia la ubicación virtual "Cliente".
- **Al Confirmar Pedido Mayorista con Seña**:
  - Se crea la `OrdenProduccion` asociada al pedido del cliente, reservando los insumos correspondientes.

## 5. Intersección Producción ⟷ Tesorería (Liquidación a Talleristas)
- **Al Finalizar una Etapa de OP (`post_save` OPEtapa a 'finalizada')**:
  - Si el tallerista es un tercero (`Contacto.tipo == 'tallerista'`), genera un devengamiento pendiente en `tesoreria` valorizado según `costo_real`, para ser liquidado en el lote de pagos semanal.

