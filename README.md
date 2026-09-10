# Indinopy — ERP/MES & Gobernanza Industrial Soberana

**Sitio Web Oficial y Documentación:** [https://indinopy.ar/](https://indinopy.ar/)

> *"Indinopy es la infraestructura tecnológica de código abierto del RIGI Conurbano: un sistema ERP/MES que convierte el trabajo real en un activo financiero inmutable (e-OP), desintermediando la usura bancaria para formalizar a las PyMEs y transferir la gobernanza de toda la cadena de valor a la comunidad productiva organizada."*

---

## 📚 Documentación Oficial

Toda la documentación arquitectónica, política y técnica (incluyendo el **Manifiesto Soberano**, el **Dossier RIGI Conurbano 2026** y los esquemas de la Mesa de Enlace Sectorial) se encuentra publicada de manera interactiva en nuestro portal oficial:

👉 **[Ingresar al Portal Indinopy.ar](https://indinopy.ar/)**

*(El código fuente de la página web y los documentos Markdown originales se encuentran en la carpeta `/docs/` de este repositorio).*

---

## 🚀 Arquitectura y Stack Tecnológico

Indinopy es un sistema de grado industrial preparado para despliegues SaaS, On-Premise y en topologías federadas (Nodos MES).

- **Backend / Core**: Python 3.12+, Django 5+ (Server Side Rendering - MVT).
- **Base de Datos**: PostgreSQL / SQLite (entorno local).
- **Inventario**: Motor de **partida doble** con ubicaciones físicas/virtuales, Quants en tiempo real, remitos y trazabilidad estricta.
- **Manufactura**: Fichas Técnicas (BOM), **Órdenes de Producción Electrónicas (e-OP)** con firma criptográfica (SHA-256), tracking por etapas, Escrow y liquidación de fasón.
- **Asincronismo**: Celery + Redis para sincronización de stock con WooCommerce (modo Headless) y procesamiento de hitos de producción (Timelocks de 48h).
- **Contabilidad y Tributación**: Módulo de partida doble preparado para ARCA/AFIP (retenciones, percepciones y liquidaciones).

---

## 📁 Módulos del Sistema (`apps/`)

El sistema está dividido en módulos atómicos interconectados:

```text
indinopy/
├── apps/
│   ├── base/          # Modelos abstractos y auditoría (HistoricalRecords)
│   ├── mes/           # Gobernanza, PTF, Nodos de Mesa de Enlace Sectorial (MES)
│   ├── documentos/    # Gestor de adjuntos, firmas criptográficas y Hash SHA-256
│   ├── contactos/     # Libreta unificada (Clientes, Talleristas, CUIT, Condición IVA)
│   ├── inventario/    # Stock por partida doble, Quants, Reservas y Remitos
│   ├── produccion/    # Recetas (BOM), e-OPs (Activo Fiduciario), hitos y liquidación
│   ├── contabilidad/  # Plan de cuentas, Libro Diario, Libro Mayor, Impuestos
│   ├── tesoreria/     # Cajas duales (Escrow Digital), cobros, pagos a talleristas
│   ├── compras/       # Órdenes de compra y recepción física de insumos
│   └── ventas/        # Pedidos B2C (WooCommerce) y B2B, motor Headless ERP
```

---

## ⚙️ Configuración y Variables de Entorno (`.env`)

El sistema utiliza un archivo `.env` en la raíz del proyecto (basado en `core/settings.py`) para definir la base de datos y la topología de red. Creá un archivo `.env` con las siguientes variables:

```ini
# Configuración Básica
SECRET_KEY=tu_clave_secreta_muy_segura
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost,tudominio.ar

# Rol del Nodo (COMITENTE, TALLERISTA, MES, DEV)
NODE_ROLE=COMITENTE

# Conexión a Base de Datos (PostGIS)
DB_NAME=indinopy
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=localhost
DB_PORT=5432
```

---

## 🛠️ Instalación y Puesta en Marcha (Recomendado: `uv`)

Indinopy es un proyecto moderno que utiliza [`uv`](https://docs.astral.sh/uv/) (el gestor ultrarrápido de paquetes en Rust) en lugar de `pip` tradicional para manejar dependencias.

### 1. Preparar el Sistema Operativo
Primero, instalá las dependencias de sistema (PostgreSQL, PostGIS, GDAL, compiladores) ejecutando el script incluido:
```bash
chmod +x install_sys_deps.sh
./install_sys_deps.sh
```

### 2. Instalar `uv`
Si aún no tenés `uv` en tu sistema, podés instalarlo con:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 3. Sincronizar Dependencias y Entorno
Con `uv`, no hace falta crear el entorno virtual a mano. Simplemente ejecutá:
```bash
# uv creará el .venv e instalará todas las dependencias del pyproject.toml / uv.lock
uv sync
```

### 4. Inicializar la Base de Datos y Correr el Servidor
Usá `uv run` para ejecutar comandos directamente en el entorno aislado del proyecto:
```bash
# Aplicar migraciones
uv run python manage.py makemigrations
uv run python manage.py migrate

# Iniciar servidor de desarrollo
uv run python manage.py runserver
```

---
*Desarrollado en el territorio fabril del Conurbano Bonaerense para las Organizaciones Libres del Pueblo.*
