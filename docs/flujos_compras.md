# Módulo de Compras y Abastecimiento

> 🧭 **Navegación**: [Índice General](README.md) ➔ [Modelos de Datos](modelos.md) ➔ **Flujos de Compras** ➔ Siguiente: [Flujos de Ventas](flujos_ventas_facturacion.md)

Este módulo asegura que la fábrica nunca se quede sin insumos, operando en estrecha relación con las Órdenes de Producción (OPs) y el Inventario.

## 1. Detección de Necesidad (Lógica MRP Básica)

Las compras en Indino responden a dos disparadores operativos:

1. **Por Proyección de OPs (BOM Dinámico)**:
   - Al confirmarse las Órdenes de Producción, el sistema calcula los insumos consolidados en `OPInsumoRequerido` e intenta reservarlos.
   - Si la `cantidad_disponible` en `StockQuant` no cubre la necesidad, se genera un requerimiento de compra automático.
2. **Por Punto de Pedido (Stock de Seguridad)**:
   - Monitoreo continuo de insumos críticos para disparar alertas preventivas de reorden.

## 2. Ciclo de Compra

1. **Orden de Compra (`OrdenCompra` que hereda de `DocumentoBase`)**:
   - Se emite con número correlativo a un proveedor registrado en `contactos.Contacto` (con CUIT y condición fiscal).
   - Contiene líneas `LineaOrdenCompra` vinculadas al SKU específico (`inventario.Producto`), con cantidad, precio unitario pactado y fecha de entrega.
   - Soporta documentos adjuntos (`GenericRelation` a `DocumentoAdjunto`), permitiendo adjuntar presupuestos en PDF o listas de precios del proveedor.

2. **Confirmación y Generación de Remito Entrante**:
   - Al pasar la `OrdenCompra` a estado `confirmado`, un signal genera automáticamente un `MovimientoStock` de tipo `recepcion` en estado `borrador`/`confirmado`.
   - Ubicación Origen: Ubicación virtual del proveedor (`tipo='proveedor'`).
   - Ubicación Destino: Depósito físico interno (`tipo='interna'`).

3. **Recepción Física, Validación de Stock y Backorders**:
   - Al llegar la mercadería al depósito, el operador valida cantidades físicas contra las líneas del movimiento.
   - **Recepción Total**: Al marcar el movimiento como `finalizado`:
     - El motor de inventario incrementa automáticamente la `cantidad_fisica` en `StockQuant`.
     - La señal actualiza `cantidad_recibida` en la `OrdenCompra` y la transiciona automáticamente a `finalizado`.
   - **Recepción Parcial (Patrón Backorder)**: Si el proveedor entrega menos de lo pedido (ej. 60 de 100 unidades):
     - El operador ejecuta `dividir_backorder({linea_id: 60})`.
     - El remito original `REC-OC-0001` asienta las 60 unidades y pasa a `finalizado`, impactando el stock de forma inmediata.
     - Se genera automáticamente un nuevo remito remanente `REC-OC-0001-B1` en estado `confirmado` por las 40 unidades faltantes.
     - La `OrdenCompra` recalcula su `porcentaje_recibido` (60%) y marca `estado_recepcion = 'parcial'`. Al completarse el backorder, la orden se cierra como `finalizado`.
   - Soporte documental: Se puede adjuntar una foto del remito en papel firmado al propio movimiento mediante `DocumentoAdjunto`.

4. **Registro de Comprobante / Factura y Tesorería**:
   - Se coteja la factura del proveedor contra las cantidades recepcionadas y los precios pactados.
   - El importe adeudado genera automáticamente un registro de pasivo en `tesoreria` para su posterior pago por transferencia, efectivo o endoso de cheques.

## 3. Evaluación de Proveedores y Precios
- Trazabilidad histórica de variaciones de costo en `HistoricalLineaOrdenCompra` y cumplimiento de plazos de entrega.

