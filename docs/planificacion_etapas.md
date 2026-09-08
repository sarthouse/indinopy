# Planificación del Proyecto (Fases de Desarrollo)

Dado el tamaño y complejidad del sistema "Indino", el desarrollo se dividirá en etapas iterativas. Cada etapa entregará un módulo funcional que aportará valor inmediato al negocio.

## Etapa 1: Fundación e Inventario Base (Semanas 1-2)
**Objetivo:** Configurar el esqueleto del proyecto y poder registrar todo el stock físico (insumos y herramientas) antes de empezar a fabricar.

1. Inicialización del proyecto Django (`django-admin startproject indinopy`).
2. Configuración de base de datos (PostgreSQL), variables de entorno y usuarios (Custom User Model).
3. Creación de la app `almacen`.
4. Modelado y ABM (CRUD) de Insumos (Cuero, Suela, etc.) y control de stock manual.
5. Modelado y ABM de Herramientas (Hormas, Sacabocados) y estados de disponibilidad.
6. Modelado de Productos Terminados (Catálogo base).

## Etapa 2: Ingeniería de Producto y Recetas (Semanas 3-4)
**Objetivo:** Digitalizar el "Know-How" de la empresa creando las Fichas Técnicas.

1. Creación de la app `produccion`.
2. Desarrollo de modelos `Receta`, `RecetaInsumo` y `RecetaEtapa`.
3. Interfaz (Django Admin o Vistas Personalizadas) para crear Recetas, permitiendo asociar insumos del `almacen` y definir el orden de las etapas de fabricación.
4. Alta de Talleristas y Proveedores (en un módulo base de `core` o `compras`).

## Etapa 3: Motor de Producción (OPs) y Tracking (Semanas 5-6)
**Objetivo:** Instanciar recetas, generar el documento principal (OP) y hacer seguimiento de las etapas.

1. Lógica de instanciación: Botón "Generar OP desde Receta" (Service Layer).
2. Generación automática de `OPInsumoRequerido` y `OPEtapaTracking`.
3. Lógica de bloqueo de stock de Insumos y cambio de estado a "En Uso" para Herramientas/Hormas.
4. Vistas HTML usando Server Side Rendering para el panel de Producción.
5. **Generación del Documento**: Integración de la plantilla `orden_produccion.html` (Vista con/sin costos dependiendo de los permisos).

## Etapa 4: Ventas B2B y B2C (Semanas 7-8)
**Objetivo:** Permitir el ingreso de dinero y automatizar la relación entre Pedidos y Producción.

1. Creación de la app `ventas` y `tesoreria`.
2. Registro de Clientes (con roles: Minorista vs Mayorista/Distribuidor).
3. Carga manual de pedidos internos.
4. Lógica de seña y caja diferida: Al registrar el pago de un Distribuidor en `tesoreria`, se dispara un *Signal* que avisa a `produccion` que puede iniciar la OP.

## Etapa 5: Integración WooCommerce y Asincronismo (Semanas 9-10)
**Objetivo:** Automatización externa y liquidaciones finales.

1. Integración de **Celery + Redis** para tareas en segundo plano.
2. Endpoints (Webhooks) para recibir pedidos desde WooCommerce.
3. Sincronización activa (enviar actualización de stock a WooCommerce cuando termina una OP).
4. Módulo de liquidación de talleristas: Al marcar etapas como "Finalizadas" en la OP, generar cuentas por pagar en `tesoreria`.
5. Testing, QA, refinamiento de interfaces y despliegue a producción.

---
*Nota: Cada etapa debe ser probada de manera aislada antes de pasar a la siguiente, garantizando que el sistema sea estable.*

