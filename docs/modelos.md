# Modelos de Datos (Django ORM)

> 🧭 **Navegación**: [Índice General](README.md) ➔ **Modelos de Datos** ➔ Siguiente: [Lógica de Negocio](logica.md) | [Arquitectura de Señales](arquitectura_signals.md)

Este documento detalla la estructura principal de la base de datos usando los modelos de **Django ORM**, reflejando la complejidad de fabricación y ventas de Indino.

## 1. Módulo Base e Infraestructura (`apps/base/models.py`)

Provee las clases abstractas maestras de las cuales heredan todos los modelos del sistema:

- **`TimeStampedModel (models.Model)`**:
  - `creado_en` (`DateTimeField`, auto_now_add=True).
  - `modificado_en` (`DateTimeField`, auto_now=True).
  - `history`: Auditoría automática de cambios con `HistoricalRecords(inherit=True)` de `simple_history`.
- **`DocumentoBase (TimeStampedModel)`**:
  - `numero` (`CharField`, identificador único comercial u operativo, ej. "OP-0001", "REM-0042").
  - `fecha` (`DateField`, fecha contable/operativa).
  - `estado` (`CharField`: `borrador`, `confirmado`, `finalizado`, `cancelado`, `anulado`).
  - `observaciones` (`TextField`).
  - `adjuntos`: `GenericRelation('documentos.DocumentoAdjunto')` permitiendo vincular remitos escaneados, fotos o PDFs a cualquier documento sin alterar esquemas.

### B. Configuración Comercial
- **`Moneda (TimeStampedModel)`**: `nombre`, `codigo` (ej. USD, ARS), `simbolo` ($), `activa`. Referencia global para cotizaciones.

---

## 2. Módulo de Documentos y Archivos (`apps/documentos/models.py`)

- **`DocumentoAdjunto (TimeStampedModel)`**:
  - Vinculación polimórfica: `content_type` y `object_id` (`GenericForeignKey`).
  - `archivo` (`FileField` con upload_to parametrizado `adjuntos/<app>/<id>/`).
  - `nombre`, `tipo_mime`, `tamano_bytes` (validación automática contra tipos inseguros y tope de 25 MB).
  - `descripcion`, `subido_por` (FK `User`).
  - Limpieza física de archivos al eliminar registros en base de datos.

---

## 3. Módulo de Contactos (`apps/contactos/models.py`)

Unifica las entidades de terceros comerciales, productivos y fiscales:

- **`CategoriaContacto`** y **`Tag`**: Segmentación y badges visuales con color hexadecimal (`color_hex`).
- **`Contacto (TimeStampedModel)`**:
  - `tipo`: `cliente`, `proveedor`, `tallerista`, `otro`.
  - Identificación comercial: `razon_social`, `nombre_fantasia`.
  - Impositivo argentino: `cuit_cuil`, `condicion_iva` (`responsable_inscripto`, `monotributo`, `exento`, `consumidor_final`, etc.).
  - Contacto: `email`, `telefono`, `direccion`, `ciudad`, `provincia`.
  - Financiero: `limite_credito` (`DecimalField`).
  - Relaciones: `tags` (M2M), `categorias` (M2M), `activo`.

---

## 4. Módulo de Inventario (`apps/inventario/models.py`)

Implementa el motor de inventario por partida doble inspirado en Odoo:

### A. Catálogo y Unidades de Medida
- **`UnidadMedida (TimeStampedModel)`**:
  - Modelo propio dinámico (supera los choices fijos).
  - `nombre` (ej. "Metro", "Par", "Kilogramo"), `simbolo` (`m`, `par`, `kg`, `u`), `tipo` (`unidad`, `longitud`, `peso`, `volumen`, `tiempo`), `activa`.
  - Auto-sembrado inicial vía señal `post_migrate`.
- **`Categoria (TimeStampedModel)`**: Árbol jerárquico (`parent`).
- **`ProductoTemplate (TimeStampedModel)`**:
  - Entidad genérica (ej. "Zapato Oxford", "Cuero Vacuno").
  - `nombre`, `codigo`, `tipo` (`almacenable`, `consumible`, `servicio`).
  - `unidad_medida` (`ForeignKey(UnidadMedida, on_delete=RESTRICT)`).
  - `tracking` (`none`, `lote`, `serie`), `categoria`, `costo_estandar`, `precio_venta`, `activo`.
  - Puntos de reposición: `stock_minimo`, `stock_maximo` y propiedad de advertencia `alerta_stock_minimo`.
- **`Atributo` y `AtributoValor`**: Dimensiones de variabilidad (Talle: 39, 40; Color: Negro, Marrón).
- **`Producto (SKU - TimeStampedModel)`**:
  - Variante física final con stock: `template` (FK), `sku` (único), `codigo_barras`, `atributos_valores` (M2M), `precio_extra`, `activo`.

### B. Ubicaciones, Lotes y Quants
- **`Ubicacion (TimeStampedModel)`**: Físicas (`interna`), Talleres Externos (`fason` con FK a `Contacto`), y Virtuales (`proveedor`, `cliente`, `produccion`, `ajuste`).
- **`Lote (TimeStampedModel)`**: Trazabilidad de partidas con fecha de vencimiento opcional.
- **`StockQuant (TimeStampedModel)`**:
  - Balance en tiempo real: `producto` (SKU), `ubicacion`, `lote`, `cantidad_fisica`, `cantidad_reservada`.
  - Propiedad calculada: `cantidad_disponible = fisica - reservada`.
  - Auto-limpieza atómica al llegar a cero para evitar registros fantasmas.

### C. Remitos, Movimientos y Backorders
- **`MovimientoStock (DocumentoBase)`**:
  - `tipo` (`recepcion`, `entrega`, `traslado`).
  - `ubicacion_origen`, `ubicacion_destino`, `contacto` (FK `contactos.Contacto`), `documento_origen`.
  - `backorder_de` (FK recursiva a `self`): Soporte nativo para entregas/recepciones parciales.
  - Método `dividir_backorder(cantidades_realizadas)`: Genera atómicamente el remito remanente pendiente y finaliza la parte cumplida.
- **`LineaMovimientoStock (TimeStampedModel)`**: `movimiento` (FK), `producto` (SKU), `lote` (opcional), `cantidad` (demandada), `cantidad_hecha` (realizada).

---

## 5. Módulo de Producción (`apps/produccion/models.py`)

Gestiona fichas técnicas, BOM con reglas de variantes y ejecución por etapas:

### A. Ingeniería (Recetas / BOM)
- **`Receta (TimeStampedModel)`**: `producto_template` (FK `ProductoTemplate`), `nombre_version`, `activa`, `observaciones_generales`.
- **`RecetaInsumo (TimeStampedModel)`**:
  - `receta` (FK).
  - `insumo` (`ForeignKey('inventario.Producto')`, SKU específico almacenable).
  - `cantidad` (`DecimalField` por unidad de producto terminado).
  - `porcentaje_merma_tolerada` (`DecimalField`, default 10.00% según estándar técnico INTI para corte/aparado).
  - `variantes_destino` (`ManyToManyField('inventario.AtributoValor', blank=True)`): Regla de variante (ej. Este insumo solo aplica a talles 42+ o color Rojo).
- **`RecetaEtapa (TimeStampedModel)`**: `receta` (FK), `orden_ejecucion`, `servicio` (FK `ProductoTemplate` tipo servicio: Corte, Aparado, etc.), `observaciones_proceso`.

### B. Ejecución de Lotes y Partes de Producción
- **`OrdenProduccion (DocumentoBase)`**:
  - `receta` (FK `Receta`), `cliente` (FK opcional `Contacto`), `fecha_entrega`.
  - `cantidad_total`, `cantidad_producida`, `porcentaje_avance`.
  - **Seguridad e Interoperabilidad e-OP (Título de Crédito Productivo)**:
    - `uuid_identificador`: UUID4 único e inmutable para intercambio inter-sistemas.
    - `hash_seguridad`: Digest criptográfico SHA-256 generado sobre payload canónico determinista JSON.
    - `regimen_juridico`: `fason_locacion_obra` (Arts. 1251 CCCN), `maquila_industrial`, `produccion_propia`.
    - `clausula_inembargabilidad`: Declaración de intangibilidad patrimonial del comitente emisor.
    - Métodos: `calcular_hash_eop()`, `sellar_hash_eop()`, `verificar_integridad_hash()`.
  - Costeo industrial: `costo_total_insumos_real`, `costo_total_fason`, `costo_total_estimado`, `costo_unitario_par`.
  - Métodos operativos:
    - `registrar_produccion_parcial()`: Habilita declarar tandas con segregación de primera calidad, segunda selección y descarte.
    - `cerrar_con_faltantes()`: Cierra reconociendo scrap y cancelando reservas sobrantes.
    - `generar_devolucion_sobrantes()`: Reingresa insumos no consumidos de la fábrica al almacén principal.
- **`OPVariacion (TimeStampedModel)`**: Curva de talles del lote (`op`, `producto` terminado SKU, `cantidad`, `cantidad_producida`, `cantidad_pendiente`).
- **`OPInsumoRequerido (TimeStampedModel)`**: `op`, `insumo` (SKU), `cantidad_teorica`, `cantidad_consumida_real`, propiedad `alerta_desvio_merma` (alerta si consumo > teórico + 10%).
- **`OPParteProduccion (TimeStampedModel)`**: Registro de tandas diarias o parciales de terminación con fecha, responsable y remito de ingreso.
- **`OPParteProduccionLinea (TimeStampedModel)`**: Desglose por variante con `cantidad` (primera selección), `cantidad_segunda` (outlet) y `cantidad_descarte` (scrap).
- **`OPEtapaTracking (TimeStampedModel)`**:
  - `op`, `etapa_origen`, `tallerista_asignado` (FK `contactos.Contacto`), `estado`.
  - Remitos: `remito_traslado` (Ida con resguardo legal CCCN de titularidad) y `remito_retorno` (Vuelta: taller ➔ fábrica).
  - `costo_servicio_total`: Liquidación de mano de obra externa.
  - Métodos: `generar_remito_traslado_taller()` y `generar_remito_retorno_taller()`.

---

## 6. Módulos Comerciales, Contables y Financieros

- **Contabilidad e Impuestos (`apps/contabilidad/models.py`)**:
  - `CondicionPago (TimeStampedModel)`: Define cronogramas de exigibilidad (ej. "30/60 días").
  - `LineaCondicionPago`: Desglose en múltiples cuotas (`porcentaje`, `monto_fijo`, `saldo`) por `dias` de plazo.
  - `Impuesto (TimeStampedModel)`: `nombre`, `tipo` (iva, retencion, percepcion, etc.), `aplicacion` (ventas, compras, ambas), `alicuota` porcentual, `activo`.

- **Compras (`apps/compras/models.py`)**:
  - `OrdenCompra (DocumentoBase)`:
    - `proveedor` (FK `contactos.Contacto` filtrado a proveedores), `fecha_entrega_esperada`.
    - `condicion_pago` (FK `contabilidad.CondicionPago`), `moneda` (FK `base.Moneda`), `tipo_cambio`, `origen_op` (FK opcional a `OrdenProduccion`).
    - Propiedades calculadas: `subtotal`, `total_iva`, `total`, `cantidad_total_pedida`, `cantidad_total_recibida`, `porcentaje_recibido`.
    - Estados dinámicos: `estado_recepcion` (`pendiente`, `parcial`, `completo`), `estado_facturacion`.
    - Métodos: `generar_recepcion_stock()` y `actualizar_cantidades_recibidas()` (sincronización con remitos y backorders).
  - `LineaOrdenCompra (TimeStampedModel)`:
    - `orden_compra` (FK), `producto` (SKU), `descripcion`, `unidad_medida` (FK `UnidadMedida`).
    - `cantidad`, `cantidad_recibida`, `cantidad_facturada`, `precio_unitario`.
    - `impuesto` (FK `contabilidad.Impuesto`).
    - Propiedades: `cantidad_pendiente`, `subtotal`, `iva_monto`, `total`.
- **Ventas (`apps/ventas/models.py`)**:
  - `PedidoVenta (DocumentoBase)`: `cliente` (FK `contactos.Contacto`), canal de venta, condición de pago (minorista contado vs. distribuidor seña).
  - `LineaPedidoVenta (TimeStampedModel)`: `pedido` (FK), `producto` (SKU), `cantidad`, `precio_unitario`.
- **Tesorería (`apps/tesoreria/models.py`)**:
  - `Caja`: Cajas oficiales (bancos, fiscal) y cajas operativas internas.
  - `MovimientoCaja (DocumentoBase)`: Ingresos (cobros, señas) y Egresos (pagos a proveedores).
  - `LiquidacionTallerista (DocumentoBase)`: Agrupación semanal de `OPEtapa` completadas por talleristas.
