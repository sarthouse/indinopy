# Conceptos del Sistema de Gestión "Indino"

> 🧭 **Navegación**: [Índice General](README.md) ➔ Anterior: [Glosario](glosario.md) ➔ **Conceptos del Sistema** ➔ Siguiente: [Estructura del Proyecto](estructura.md)

Este documento define la arquitectura general, los objetivos y la estructura modular del sistema de gestión (ERP/CRM) basado en **Django (Server Side Rendering)**.

## 1. Visión General y Negocio
- **Objetivo**: Sistema de gestión modular enfocado en la manufactura dual (minorista/mayorista) y control de talleres.
- **Stack Principal**: Python, Django, PostgreSQL, HTML/CSS (Server Side Rendering), Celery (Tareas Asíncronas).
- **Integración Principal**: WooCommerce (para ventas minoristas).

## 2. Arquitectura Modular (Django Apps)
El sistema está dividido en "Apps" de Django para separar lógicamente los departamentos y la infraestructura de la empresa:

- **`base`**: Abstracciones transversales (`TimeStampedModel` con trazabilidad histórica automática vía `simple_history` y `DocumentoBase` con máquina de estados y adjuntos).
- **`documentos`**: Almacenamiento y vinculación de archivos adjuntos (imágenes, PDFs, fichas) con `GenericForeignKey` y validación de tipos MIME y tamaño (hasta 25 MB).
- **`contactos`**: Libreta unificada de Clientes, Proveedores y Talleristas con campos fiscales argentinos (CUIT/CUIL, Condición IVA, Límite de crédito).
- **`inventario`**: Motor de stock por partida doble (Odoo-style) con `UnidadMedida` dinámica, `ProductoTemplate`, variantes `Producto` (SKU), `StockQuant` (balance en tiempo real) y remitos (`MovimientoStock`).
- **`produccion`**: El núcleo de manufactura. Gestión de Fichas Técnicas (`Receta`), BOM con selección de variantes (`variantes_destino`), Órdenes de Producción (`OP`), tracking de etapas y asignación a talleristas.
- **`compras`**: Adquisición de insumos basada en requerimientos de OPs y reglas de reabastecimiento, con generación de remitos entrantes.
- **`ventas`**: Gestión de pedidos omnicanal, políticas de precios diferenciadas (Final vs. Distribuidor) y estrategia Make to Order.
- **`tesoreria`**: Manejo de cajas duales (oficial/extraoficial), cobros diferidos (señas) y liquidación automatizada por etapa a talleristas.

## 3. Patrones de Diseño en Django
- **MVT (Model-View-Template)**: Renderizado del frontend directamente desde el servidor usando los templates de Django.
- **Fat Models, Skinny Views / Capa de Servicios**: Lógica de negocio encapsulada en métodos de los modelos o en archivos `services.py` dentro de cada app, evitando vistas sobrecargadas.
- **Auditoría Integral (simple-history)**: Todas las entidades críticas heredan historial de versiones completo.
- **Doble Partida y Quants de Inventario**: El inventario no tiene un contador estático; se calcula por sumatoria de ubicaciones origen y destino en `StockQuant`.
- **ACL (Control de Acceso) Estricto**: Manejo de permisos para que roles operativos (ej. Talleristas) no vean información clasificada (costos).
