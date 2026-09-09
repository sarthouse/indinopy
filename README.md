# Indinopy — ERP & MES Industrial para Manufactura

Sistema de Planificación de Recursos Empresariales (ERP) y Ejecución de Manufactura (MES) desarrollado con **Django**, especializado en producción manufacturera (calzado, indumentaria y marroquinería), control de talleres externos (fasón), inventario por partida doble estilo Odoo, compras, tesorería y comercio omnicanal.

---

## 🚀 Arquitectura y Stack Tecnológico

- **Backend**: Python 3.12+, Django 5+ (Server Side Rendering - MVT).
- **Base de Datos**: PostgreSQL / SQLite (entorno local).
- **Auditoría Integral**: `django-simple-history` para seguimiento histórico automático en todos los modelos.
- **Inventario**: Motor de partida doble con ubicaciones físicas/virtuales, Quants en tiempo real y Lotes.
- **Manufactura**: Fichas Técnicas (BOM) dinámicas con reglas de variantes (`variantes_destino`), Órdenes de Producción (OP) con tracking por etapas y liquidación de fasón.
- **Asincronismo**: Celery + Redis para sincronización de stock con WooCommerce y reportes.

---

## 📚 Documentación del Sistema

Toda la documentación técnica, arquitectónica y operativa se encuentra centralizada e interconectada en la carpeta [`docs/`](docs/README.md):

👉 **[Ver Centro de Documentación y Mapa de Navegación (`docs/README.md`)](docs/README.md)**

### Accesos Rápidos
- 📖 [**Glosario Industrial y Técnico**](docs/glosario.md): Analogías para principiantes sobre SKUs, Quants, BOM y Fasón.
- 💡 [**Conceptos Generales**](docs/conceptos.md): Objetivos y filosofía de diseño.
- 📂 [**Estructura del Proyecto**](docs/estructura.md): Árbol de aplicaciones (`apps/`).
- 🧱 [**Modelos de Datos (ORM)**](docs/modelos.md): Catálogo completo de entidades y relaciones.
- ⚙️ [**Lógica de Negocio y Fórmulas BOM**](docs/logica.md): Fórmulas de cálculo dinámico y reservas.
- ⚡ [**Arquitectura de Señales**](docs/arquitectura_signals.md): Receptores atómicos para sincronización entre apps.
- 🏭 [**Guía Rápida Operativa**](docs/manuales/guia_rapida_operativa.md): Simulación paso a paso de un lote real de 100 pares de borcegos.
- 📋 [**Recopilación Integral del Sistema**](docs/recopilacion_sistema.md): Blueprint global y diagramas de secuencia.

---

## 📁 Módulos del Sistema (`apps/`)

```text
indinopy/
├── apps/
│   ├── base/          # Modelos abstractos: TimeStampedModel y DocumentoBase
│   ├── documentos/    # GenericForeignKey para archivos adjuntos (hasta 25 MB)
│   ├── contactos/     # Libreta unificada (Clientes, Proveedores, Talleristas, CUIT, IVA)
│   ├── inventario/    # Stock por partida doble, UnidadMedida, Quants, Remitos
│   ├── produccion/    # Recetas (BOM), OPs, variaciones de lote, etapas y fasón
│   ├── compras/       # Órdenes de compra y recepción física de insumos
│   ├── ventas/        # Pedidos B2C (WooCommerce) y B2B (Make to Order con seña)
│   └── tesoreria/     # Cajas duales (oficial/planta), cobros y liquidación de talleristas
```

---

## 🛠️ Comandos de Desarrollo

```bash
# Activar entorno virtual
source .venv/bin/activate

# Crear migraciones
python manage.py makemigrations

# Aplicar migraciones
python manage.py migrate

# Iniciar servidor de desarrollo
python manage.py runserver
```
