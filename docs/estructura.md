# Estructura del Proyecto (Django SSR)

Al utilizar **Django**, adoptaremos su estructura estándar de "Proyecto y Aplicaciones", que encaja perfectamente con la división departamental de Indino.

## Árbol de Directorios Propuesto

```text
indinopy/
├── manage.py                   # Punto de entrada de Django
├── requirements.txt            # Dependencias
├── core/                       # (Proyecto Django) Configuraciones globales
│   ├── settings.py             # Configuración (Apps, DB, Templates, Celery)
│   ├── urls.py                 # Enrutador principal
│   └── wsgi.py / asgi.py
│
├── apps/                       # --- Módulos de Negocio (Django Apps) ---
│   │
│   ├── ventas/                 # Pedidos, Clientes, WooCommerce integration
│   │   ├── models.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   ├── services.py         # Lógica compleja de negocio
│   │   └── webhooks.py         # Recepción de webhooks de Woo
│   │
│   ├── compras/                # Proveedores y Órdenes de Compra
│   │   └── ...
│   │
│   ├── produccion/             # OPs, Etapas, Talleristas
│   │   ├── models.py
│   │   ├── views.py
│   │   ├── forms.py            # Formularios para ABM y tracking
│   │   └── urls.py
│   │
│   ├── almacen/                # Inventario (Insumos, Terminados, Herramientas)
│   │   └── ...
│   │
│   └── tesoreria/              # Cajas, Pagos y Liquidaciones
│       └── ...
│
├── templates/                  # Plantillas Globales (Server Side Rendering)
│   ├── base.html               # Layout principal (Menú, Sidebar)
│   └── produccion/             
│       └── orden_produccion.html # Plantilla de impresión dual (con/sin costos)
│
└── static/                     # Archivos estáticos (CSS, JS, Imágenes)
    ├── css/
    └── img/
```

## Por qué esta estructura:
1. **`apps/`**: Agrupar las aplicaciones dentro de una carpeta mantiene la raíz limpia. Cada departamento tiene su propia app, facilitando el mantenimiento.
2. **`templates/`**: Al usar SSR, los HTML viven centralizados o dentro de cada app. Aquí residirán documentos como `orden_produccion.html`.
3. **`services.py`**: Django no lo incluye por defecto, pero lo agregamos para sacar lógica pesada de las `views.py` (ej. la liquidación de una OP).
