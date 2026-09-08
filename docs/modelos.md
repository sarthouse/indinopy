# Modelos de Datos (Django ORM)

Este documento detalla la estructura principal de la base de datos usando los modelos de **Django ORM**, reflejando la complejidad de fabricación y ventas de Indino.

## 1. Módulo de Producción (`apps/produccion/models.py`)

El flujo de producción se basa en plantillas maestras (Recetas) que luego se instancian en Órdenes de Producción (OPs) reales.

### A. Ingeniería y Fichas Técnicas (Plantillas)
- **`Receta (Ficha Técnica)`**: Define CÓMO se fabrica un Producto.
  - Campos: `producto` (FK), `nombre_version` (ej. "Invierno 2024"), `observaciones_generales`.
- **`RecetaInsumo`**: La lista de materiales (BOM).
  - Campos: `receta` (FK), `insumo` (FK a Almacén), `cantidad_base` (por cada par/unidad).
- **`RecetaEtapa`**: Hoja de ruta de fabricación.
  - Campos: `receta` (FK), `orden_ejecucion` (1, 2, 3...), `nombre_proceso` (Corte, Aparado), `tallerista_predeterminado` (FK opcional), `observaciones_proceso` (instrucciones técnicas).

### B. Ejecución de Lotes (Producción Real)
- **`OrdenProduccion (OP)`**: Nace al clonar/instanciar una `Receta`.
  - Campos: `numero_op`, `fecha_emision`, `fecha_entrega`, `receta_base` (FK), `cliente` (opcional), `cantidad_total`, `estado` (Pendiente, En Proceso, Finalizada).
  - Herramientas: Relación temporal (ej. asignación de Hormas de Almacén).
- **`OPVariacion`**: Curva de talles de este lote (Talle, Color, Cantidad).
- **`OPEtapaTracking`**: Instanciado de `RecetaEtapa`.
  - Campos: `op` (FK), `etapa_origen` (copiada de Receta), `tallerista_real` (FK), `estado`, `costo_servicio`, `observaciones_ejecucion`.
- **`OPInsumoRequerido`**: Instanciado de `RecetaInsumo` y multiplicado por la `cantidad_total`.
  - Campos: `op` (FK), `insumo` (FK), `cantidad_teorica`, `cantidad_consumida_real`.

## 2. Módulo de Catálogo y Almacén (`apps/almacen/models.py`)

Inspirado en la arquitectura de Odoo, unificamos el concepto de "Insumo", "Servicio" y "Producto Terminado" bajo un mismo paraguas de catálogo, diferenciándolos por su "Tipo".

### A. Productos y Variantes (Core del Catálogo)
- **`ProductoTemplate`** (Producto Base): La entidad comercial genérica (ej. "Zapato de Vestir").
  - Campos: `nombre`, `codigo_interno`, `tipo_producto` (Almacenable, Consumible, Servicio), `unidad_medida` (Unidades, Metros, Horas), `precio_venta_base`, `costo_base`.
- **`ProductoAtributo`** y **`AtributoValor`**: Definen las dimensiones de variación. (Ej. Atributo: "Talle", Valores: "39", "40").
- **`Producto (SKU)`**: La combinación real que maneja stock (ej. "Zapato de Vestir - Negro - 39"). Representa la variante específica.
  - Campos: `template` (FK), `sku` (Código único), `codigo_barras`, `precio_extra` (recargo por variante).

### B. Herramientas y Activos
- **`Herramienta`**: Hormas, sacabocados. Entidades que no se consumen sino que se prestan/asignan temporalmente a una OP.

*Nota de Arquitectura:* Bajo esta estructura, el cuero es un `ProductoTemplate` de tipo "Almacenable" con unidad "Metros", el servicio de un tallerista (ej. "Aparado") es un `ProductoTemplate` de tipo "Servicio" con unidad "Unidades" (pares), y el zapato terminado es un `ProductoTemplate` "Almacenable" con Variantes (Talle/Color).

## 3. Módulo de Ventas y CRM (`apps/ventas/models.py`)

- **`Cliente`**: Datos del cliente, con un campo `tipo` (Minorista, Distribuidor).
- **`Pedido`**: Puede venir de WooCommerce o manual. Minoristas pagan 100%, Mayoristas dejan seña.

## 4. Módulo de Tesorería (`apps/tesoreria/models.py`)

- **`MovimientoCaja`**: Entradas y salidas.
- **`LiquidacionTallerista`**: Registro de pagos generados a partir de las etapas completadas en `OPEtapaTracking`.
