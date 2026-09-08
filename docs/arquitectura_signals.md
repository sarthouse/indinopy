# Arquitectura de Señales y Automatización (Estilo Odoo)

En un ERP moderno como Odoo, los módulos casi no hablan entre sí de forma síncrona manual, sino que reaccionan a eventos. En Django, esto se logra mediante **Signals** (Señales) o llamando a **Servicios** en los cambios de estado.

A continuación, el mapa de las señales críticas que necesitaremos programar para que Indino funcione en "piloto automático":

## 1. Intersección Producción ⟷ Almacén
*   **Al Confirmar una OP (`post_save` OrdenProduccion a 'en_proceso')**:
    *   *Acción*: Leer todos los `OPInsumoRequerido`.
    *   *Efecto*: Crear automáticamente `MovimientosStock` en estado 'reservado' desde el Almacén hacia la ubicación virtual "Producción".
*   **Al Finalizar una OP (`post_save` OrdenProduccion a 'finalizada')**:
    *   *Acción A (Consumo)*: Pasar los movimientos de insumos de 'reservado' a 'realizado' (descuenta el físico).
    *   *Acción B (Ingreso)*: Crear movimientos en estado 'realizado' para las `OPVariacion` (los zapatos terminados), desde la ubicación virtual "Producción" hacia el Almacén.

## 2. Intersección Ventas ⟷ Almacén / Producción (Make to Order)
*   **Al Confirmar un Pedido Minorista (`post_save` Pedido a 'pagado')**:
    *   *Acción*: Genera el `MovimientoStock` de salida (Remito) en estado 'realizado' para descontar el stock del producto vendido.
*   **Al Pagar Seña un Mayorista (`post_save` Pedido a 'seña_pagada')**:
    *   *Acción (Make to Order)*: El sistema detecta que es un pedido mayorista a fabricar, clona la `Receta` correspondiente y genera automáticamente una `OrdenProduccion` en estado 'borrador' conectada a este cliente.

## 3. Intersección Almacén ⟷ Compras (Reglas de Reabastecimiento / MRP)
*   **Al Actualizar un StockQuant (`post_save` StockQuant)**:
    *   *Condición*: Si `(cantidad_fisica - cantidad_reservada) < stock_minimo_configurado`.
    *   *Acción*: Generar automáticamente un "Requerimiento de Compra" (Draft Purchase Order) en el módulo de Compras para el proveedor predeterminado de ese insumo. Esto evita que la fábrica se quede sin materiales (Reglas de Reorden de Odoo).

## 4. Intersección Producción ⟷ Tesorería (Liquidación a Talleristas)
*   **Al Finalizar una Etapa de OP (`post_save` OPEtapaTracking a 'finalizada')**:
    *   *Condición*: Si el tallerista es externo (Fasón o Tallerista satélite).
    *   *Acción*: Generar una "Cuenta por Pagar" o "Liquidación Pendiente" en el módulo de Tesorería a nombre de ese tallerista, por el monto del `costo_servicio_total`. Así, el viernes Tesorería solo presiona "Pagar" y tiene todas las micro-tareas agrupadas.

## 5. Intersección Compras ⟷ Almacén ⟷ Tesorería
*   **Al Aprobar Orden de Compra (`post_save` OC a 'aprobada')**:
    *   *Acción*: Genera un `MovimientoStock` entrante en estado 'reservado' (Stock futuro/entrante).
*   **Al Recibir Factura del Proveedor**:
    *   *Acción*: Genera la Cuenta por Pagar en Tesorería.

