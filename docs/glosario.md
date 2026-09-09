# Glosario Integral de Indinopy ERP
## Diccionario de Conceptos para Principiantes, Desarrolladores y Operarios

> 🧭 **Navegación**: [Índice General](README.md) ➔ **Glosario** ➔ Siguiente: [Conceptos del Sistema](conceptos.md) | [Guía Rápida Operativa](manuales/guia_rapida_operativa.md)

Este glosario explica los términos técnicos y comerciales utilizados en el sistema Indinopy, utilizando analogías sencillas de la industria del calzado y textil para facilitar el entendimiento de todo el equipo.

---

## 1. Catálogo y Productos

### ProductoTemplate (Plantilla Base)
* **¿Qué es?** Es la idea conceptual o el modelo general del producto, sin especificar aún su color o talle.
* **Analogía:** *"Zapato Oxford de Cuero"* o *"Remera Lisa de Algodón"*.
* **Para qué sirve:** Define el nombre general, la categoría, el costo base, la unidad de medida y si es almacenable o un servicio.

### Producto (Variante / SKU)
* **¿Qué es?** Es el artículo físico real y exacto que existe en el mundo real, con atributos definidos. Viene con su código de barras o SKU (*Stock Keeping Unit*).
* **Analogía:** *"Zapato Oxford - Negro - Talle 40"*.
* **Para qué sirve:** Es lo que realmente se cuenta en los estantes del almacén, se vende en WooCommerce y se mete en una caja.

### Atributo y AtributoValor
* **¿Qué son?** Las características que diferencian a una variante de otra.
* **Ejemplos:**
  * Atributo: **Talle** ➔ Valores: `39`, `40`, `41`, `42`.
  * Atributo: **Color** ➔ Valores: `Negro`, `Suela`, `Marrón Chocolate`.

### UnidadMedida (UdM)
* **¿Qué es?** El estándar físico en el que se mide, compra o consume un producto.
* **Ejemplos:** `Pares` (para zapatos terminados), `Metros` (para rollos de tela/elástico), `Kilogramos` (para pegamento o tintas), `Unidades` (para cajas o etiquetas), `Horas` (para servicios de talleristas).

---

## 2. Manufactura y Producción

### Receta (Ficha Técnica / BOM - Bill of Materials)
* **¿Qué es?** La fórmula maestra de cómo se fabrica 1 unidad de un producto base.
* **Analogía:** La receta de cocina de un pastel. Te dice: *"Para hacer 1 par de este zapato necesitas 0.25 m² de cuero vacuno, 0.05 litros de pegamento, y debe pasar por Corte, Rebajado y Aparado"*.
* **No cambia en el día a día:** Es la plantilla estándar que diseña el modelista.

### OrdenProduccion (OP / Lote de Fabricación)
* **¿Qué es?** La orden de trabajo concreta para mandar a fabricar una cantidad específica en una fecha determinada.
* **Analogía:** *"Mandar a fabricar 200 pares del Zapato Oxford para la temporada Invierno 2026"*.
* **Estructura dual:**
  * **Original:** Vista para la administración con costos, precios y márgenes valorizados.
  * **Duplicado:** Hoja de ruta para los talleristas, **sin costos ni precios**, solo con cantidades e instrucciones técnicas de proceso.

### OPVariacion (Curva de Talles)
* **¿Qué es?** El desglose exacto de cuántas unidades de cada talle y color componen la OP.
* **Ejemplo:** En una orden de 100 pares: 20 pares del Talle 39, 40 pares del Talle 40 y 40 pares del Talle 41.

### Variantes Destino (Reglas de Insumos)
* **¿Qué es?** La capacidad de una receta de decir: *"Este insumo solo se usa si el zapato que se fabrica tiene cierto atributo"*.
* **Ejemplo:** 
  * Si el zapato es **Negro**, consume **Cuero Negro**.
  * Si el zapato es **Marrón**, consume **Cuero Marrón**.
  * La **Etiqueta de Marca** no tiene filtro: se gasta en todos los pares por igual.

### Fasón (Maquila / Tercerización)
* **¿Qué es?** El esquema de trabajo donde Indino contrata a un taller externo para realizar una etapa o la totalidad del producto.
* **Caso A (Fasón con insumo propio):** Indino le entrega el cuero cortado al tallerista y el tallerista solo cobra su mano de obra (Servicio).
* **Caso B (Fasón con insumo provisto por ellos):** El tallerista compra los cierres o hilos por su cuenta y luego se los factura a Indino.

---

## 3. Almacén e Inventario

### Inventario por Partida Doble
* **¿Qué es?** Principio contable aplicado a la mercadería: **el stock nunca aparece de la nada ni se esfuma mágicamente**. Todo movimiento tiene un **Origen** y un **Destino**.
* **Ejemplos:**
  * *Compra:* De Proveedor (Virtual) ➔ Almacén Central (Físico).
  * *Consumo OP:* De Almacén Central (Físico) ➔ Fábrica/Producción (Virtual).
  * *Pérdida/Robo:* De Almacén Central (Físico) ➔ Pérdida/Ajuste (Virtual).

### Ubicación (Física vs Virtual)
* **Ubicación Física:** Lugares reales donde puedes tocar la mercadería (ej. *Almacén Central*, *Estantería B*).
* **Ubicación Virtual:** Cuentas abstractas que representan a las entidades externas (ej. *Ubicación Proveedores*, *Ubicación Clientes*, *Ubicación Producción*).

### StockQuant (El Balance en Tiempo Real)
* **¿Qué es?** Es la "foto instantánea" del stock en un lugar exacto.
* **Analogía:** Es la tarjeta o etiqueta física pegada en un estante que dice: *"En este estante hay 45 pares del SKU ZAP-NEG-40"*.
* **Cálculo automático:**
  * `cantidad_fisica`: Lo que realmente hay en el estante.
  * `cantidad_reservada`: Lo que ya está comprometido para una OP o un pedido de cliente.
  * `cantidad_disponible`: `Física - Reservada` (lo que todavía puedes prometer o vender).

### MovimientoStock (Remito / Picking) y Línea de Movimiento
* **MovimientoStock (Cabecera):** El documento comercial o remito de traslado (ej: Remito N° R-0001-00004523). Dice a dónde va la carga y si es Fiscal (AFIP) o Interno (X).
* **LineaMovimientoStock:** Cada renglón dentro de ese remito (ej: 20 pares del Talle 39, 15 pares del Talle 40).

---

## 4. Auditoría y Trazabilidad

### TimeStampedModel
* **¿Qué es?** Clase base que inyecta automáticamente la fecha y hora de creación (`creado_en`) y de última modificación (`modificado_en`) en cualquier tabla del ERP.

### DocumentoBase
* **¿Qué es?** Clase base para todos los documentos con ciclo de vida (Remitos, OPs, Pedidos, Órdenes de Compra).
* **Ciclo de vida:** `borrador` ➔ `confirmado` ➔ `finalizado` (o `cancelado`/`anulado`).

### Simple History (Auditoría Forense)
* **¿Qué es?** Sistema de grabación continua. Cada vez que alguien cambia un precio, anula un remito o edita una OP, el sistema guarda una copia exacta de cómo estaba antes, qué usuario lo hizo y en qué segundo exacto ocurrió.
