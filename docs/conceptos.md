# Conceptos del Sistema de Gestión "Indino"

Este documento define la arquitectura general, los objetivos y la estructura modular del sistema de gestión (ERP/CRM) basado en **Django (Server Side Rendering)**.

## 1. Visión General y Negocio
- **Objetivo**: Sistema de gestión modular enfocado en la manufactura dual (minorista/mayorista) y control de talleres.
- **Stack Principal**: Python, Django, PostgreSQL, HTML/CSS (Server Side Rendering), Celery (Tareas Asíncronas).
- **Integración Principal**: WooCommerce (para ventas minoristas).

## 2. Arquitectura Modular (Django Apps)
El sistema estará dividido en "Apps" de Django para separar lógicamente los departamentos de la empresa:

- **`ventas`**: Gestión de pedidos omnicanal, listas de precios diferenciadas (Final vs. Distribuidor).
- **`compras`**: Adquisición de insumos basada en Órdenes de Producción.
- **`produccion`**: El núcleo. Gestión de la Orden de Producción (OP), control del Lote, tracking de etapas y asignación a talleristas.
- **`almacen`**: Control de stock de insumos, productos terminados y herramientas (ej. Hormas).
- **`tesoreria`**: Manejo de cajas, cobros diferidos (señas de distribuidores) y liquidación a talleristas.

## 3. Patrones de Diseño en Django
- **MVT (Model-View-Template)**: Renderizado del frontend directamente desde el servidor usando los templates de Django.
- **Fat Models, Skinny Views / Capa de Servicios**: Lógica de negocio encapsulada en métodos de los modelos o en archivos `services.py` dentro de cada app, evitando vistas sobrecargadas.
- **ACL (Control de Acceso) Estricto**: Manejo de permisos para que roles operativos (ej. Talleristas) no vean información clasificada (costos).
