# Lógica de Negocio y Flujos

> 🧭 **Navegación**: [Índice General](README.md) ➔ Anterior: [Modelos de Datos](modelos.md) ➔ **Lógica de Negocio** ➔ Siguiente: [Arquitectura de Señales](arquitectura_signals.md) | [Guía Rápida Operativa](manuales/guia_rapida_operativa.md)

En Django, la lógica compleja se maneja mediante señales y capas de servicios (`services.py`) para orquestar la relación entre las Fichas Técnicas (Recetas), la Producción y el Inventario.

## 1. Generación y Ciclo de Vida de la Orden de Producción (OP)

La creación de una `OrdenProduccion` (OP) es un proceso automatizado respaldado por señales atómicas:

1. **Instanciación de la OP**:
   - Se crea la `OrdenProduccion` seleccionando una `Receta` activa (que define el Producto Base / Template).
   - Se cargan las variaciones específicas a fabricar mediante registros `OPVariacion` (especificando los SKUs finales, ej. talles y colores con sus cantidades).
   - Se instancian las etapas en `OPEtapa` a partir de las `RecetaEtapa`.

2. **Cálculo Dinámico de Insumos (`calcular_insumos_requeridos_op`)**:
   - Al pasar la OP a estado `confirmado` (o invocar el cálculo), el sistema itera por cada `OPVariacion`.
   - Evalúa cada `RecetaInsumo`: si `variantes_destino` está vacío, el insumo aplica a todas las unidades; si contiene atributos específicos (ej. "Talle 42" o "Color Negro"), solo se computa si la variante destino posee dichos atributos.
   - Suma y consolida las cantidades exactas en registros `OPInsumoRequerido(insumo=SKU, cantidad_requerida)`.

3. **Reserva Automática en Inventario (`reservar_insumos_op`)**:
   - Inmediatamente, la señal genera un `MovimientoStock` de tipo `produccion` en estado `confirmado` (reserva).
   - Origen: Ubicación Física Interna (ej. "Depósito Central").
   - Destino: Ubicación Virtual de Producción (ej. "Línea de Armado / Fasón").
   - El motor de inventario incrementa `StockQuant.cantidad_reservada` y reduce `cantidad_disponible`, garantizando que ningún otro proceso consuma los materiales comprometidos.

4. **Finalización y Alta de Producto Terminado (`ejecutar_produccion_op`)**:
   - Al marcar la OP como `finalizado`:
     - **Consumo Real**: El `MovimientoStock` de insumos pasa a `finalizado`, deduciendo `cantidad_fisica` y liberando la reserva en el Quant.
     - **Ingreso de Terminados**: Se genera y finaliza automáticamente un `MovimientoStock` desde la ubicación virtual "Producción" hacia la ubicación física interna con los SKUs y cantidades definidos en `OPVariacion`.

## 2. Flujo Diferenciado de Ventas (Minorista vs Mayorista)
- **Minorista (B2C)**: El pedido entra pagado (WooCommerce / Mostrador) y genera un remito de entrega inmediato desde el stock disponible.
- **Distribuidor (B2B / Make to Order)**: El pedido mayorista requiere seña. Al confirmarse el cobro inicial en Tesorería, el sistema genera la OP asociada. Al fabricarse el lote, se cobra el saldo contraentrega y se despacha.

## 3. Seguimiento de Etapas y Liquidación a Talleristas
- Cada `OPEtapa` representa un proceso (Corte, Aparado, Rebajado) con un tallerista asignado (`contactos.Contacto`).
- Al finalizar la etapa, se registra el `costo_real` de la mano de obra.
- Tesorería agrupa semanalmente todas las etapas finalizadas por tallerista para emitir una única orden de pago o liquidación.

## 4. Adjuntos y Trazabilidad Transversal
- Cualquier documento (`OrdenProduccion`, `MovimientoStock`, etc.) permite adjuntar archivos directamente (`op.adjuntos.create(archivo=...)`), guardando fotos del corte, remitos firmados por choferes o especificaciones de matricería.
- Cada cambio en modelos `TimeStampedModel` queda registrado en tablas históricas vía `simple_history`.
