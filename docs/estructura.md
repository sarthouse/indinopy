# Estructura del Proyecto (Django SSR)

> 🧭 **Navegación**: [Índice General](README.md) ➔ Anterior: [Conceptos del Sistema](conceptos.md) ➔ **Estructura del Proyecto** ➔ Siguiente: [Modelos de Datos](modelos.md)

Al utilizar **Django**, adoptaremos su estructura estándar de "Proyecto y Aplicaciones", que encaja perfectamente con la división departamental de Indino.

## Árbol de Directorios del Sistema

```text
indinopy/
├── manage.py                   # Punto de entrada de Django
├── requirements.txt            # Dependencias del proyecto
├── core/                       # (Proyecto Django) Configuraciones globales
│   ├── settings.py             # Configuración (Apps, DB, Media, simple_history, Celery)
│   ├── urls.py                 # Enrutador principal y servicio de media en DEBUG
│   └── wsgi.py / asgi.py
│
├── apps/                       # --- Módulos de Negocio (Django Apps) ---
│   │
│   ├── base/                   # Infraestructura y abstracciones comunes
│   │   ├── models.py           # TimeStampedModel (simple_history) y DocumentoBase (estados + adjuntos)
│   │   └── apps.py
│   │
│   ├── documentos/             # Gestión transversal de archivos y adjuntos
│   │   ├── models.py           # DocumentoAdjunto (GenericForeignKey, validación MIME, max 25MB)
│   │   ├── apps.py
│   │   └── admin.py
│   │
│   ├── contactos/              # Libreta unificada de relaciones comerciales y fiscales
│   │   ├── models.py           # Contacto (Cliente, Proveedor, Tallerista, CUIT, Condición IVA), Categoria, Tag
│   │   ├── apps.py
│   │   └── admin.py
│   │
│   ├── inventario/             # Núcleo de stock por partida doble (Odoo-style)
│   │   ├── models.py           # UnidadMedida, ProductoTemplate, Producto (SKU), Ubicacion, Lote, StockQuant, MovimientoStock, LineaMovimientoStock
│   │   ├── signals.py          # Actualización atómica de StockQuant (reservas/físico) y semillas de unidades
│   │   ├── apps.py
│   │   └── admin.py
│   │
│   ├── produccion/             # Manufactura, Fichas Técnicas (BOM), OPs y Fasón
│   │   ├── models.py           # Receta, RecetaInsumo (con variantes_destino), RecetaEtapa, OrdenProduccion, OPVariacion, OPInsumoRequerido, OPEtapa
│   │   ├── signals.py          # Cálculo automático de insumos requeridos y reserva en inventario
│   │   ├── apps.py
│   │   └── admin.py
│   │
│   ├── compras/                # Abastecimiento y relación con proveedores
│   │   ├── models.py           # OrdenCompra (DocumentoBase), LineaOrdenCompra
│   │   ├── signals.py          # Generación automática de MovimientoStock de recepción al confirmar
│   │   └── apps.py
│   │
│   ├── ventas/                 # Pedidos omnicanal (B2B / B2C) e integración WooCommerce
│   │   ├── models.py           # PedidoVenta, LineaPedidoVenta
│   │   ├── services.py         # Lógica comercial y Make to Order
│   │   ├── webhooks.py         # Recepción y validación de webhooks de WooCommerce
│   │   └── apps.py
│   │
│   └── tesoreria/              # Cajas duales (oficial/interna), cobros y liquidación de talleristas
│       ├── models.py           # Caja, MovimientoCaja, CuentaCorriente, LiquidacionTallerista
│       └── apps.py
│
├── media/                      # Archivos subidos por usuarios (adjuntos de documentos, fichas técnicas)
│   └── adjuntos/               # Estructurados por {app_label}/{object_id}/
│
├── templates/                  # Plantillas Globales (Server Side Rendering)
│   ├── base.html               # Layout principal (Sidebar, Breadcrumbs, Notificaciones)
│   └── produccion/             
│       └── orden_produccion.html # Plantilla dual imprimible (Original con costos / Duplicado ciego)
│
└── static/                     # Archivos estáticos (CSS, JS, iconos, logos)
    ├── css/
    └── img/
```

## Por qué esta estructura:
1. **`apps/` con especialización modular**: Cada dominio de negocio vive en su propia app. `base`, `documentos` y `contactos` proporcionan la infraestructura común sobre la cual descansan `inventario`, `produccion`, `compras`, `ventas` y `tesoreria`.
2. **Generic Relations para archivos (`apps/documentos`)**: Permite que cualquier documento (una `OrdenProduccion`, un `MovimientoStock` o una futura `OrdenCompra`) soporte archivos adjuntos sin duplicar campos `FileField` ni modificar esquemas existentes.
3. **Auditoría continua**: Mediante `TimeStampedModel` y `simple_history`, todos los registros cuentan con trazabilidad histórica completa sin intervención manual.
4. **Separación de responsabilidades (`signals.py` y `services.py`)**: Desacopla la lógica de sincronización entre módulos (por ejemplo, producción reservando stock) sin acoplar fuertemente los modelos.
