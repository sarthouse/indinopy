# Módulo de Compras y Abastecimiento

Este módulo asegura que la fábrica nunca se quede sin insumos, operando en estrecha relación con las Órdenes de Producción (OPs) y el Almacén.

## 1. Detección de Necesidad (Lógica MRP Básica)

Las compras en Indino no se hacen a ciegas. Existen dos disparadores automáticos:

1. **Por Punto de Pedido (Stock Mínimo)**: 
   - Cada Insumo en el Almacén tiene un `stock_minimo`. Si el inventario cae por debajo de este número, el sistema lanza una alerta de reposición a Compras.
2. **Por Proyección de OPs (BOM)**:
   - Al aprobarse múltiples OPs (ej. "Fabricar 1000 pares"), el sistema suma todos los `OPInsumoRequerido` de las OPs en cola. 
   - Si se necesitan 500 metros de cuero y en stock hay 200, el sistema genera automáticamente una sugerencia de compra por 300 metros.

## 2. Ciclo de Compra

1. **Orden de Compra (OC)**:
   - Compras genera una OC dirigida a un Proveedor (ej. "Curtiembre SA").
   - Detalla cantidades, precios pactados y fechas de entrega esperadas.
   
2. **Recepción de Mercadería**:
   - Cuando el camión llega, el usuario de Almacén coteja el Remito del proveedor contra la OC del sistema.
   - Si es correcto, aprueba la entrada. El stock del Almacén se incrementa automáticamente.

3. **Registro de Factura de Compra**:
   - Administración ingresa la Factura del proveedor (o el comprobante interno de gasto).
   - Este paso valida si el precio cobrado coincide con el precio pactado en la OC.
   - Inmediatamente se genera una **Cuenta por Pagar** en el módulo de Tesorería.

## 3. Evaluación de Proveedores
El sistema guardará historial de tiempos de entrega y variaciones de precio para sugerir a qué proveedor comprarle la próxima vez.

