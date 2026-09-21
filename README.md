# Indinopy — ERP/MES & Gobernanza Industrial Soberana

**Sitio Web Oficial y Documentación:** [https://indinopy.ar/](https://indinopy.ar/)

> *"Indinopy es una infraestructura tecnológica de código abierto diseñada para el incentivo y la formalización de la manufactura del calzado argentino. Es un sistema ERP/MES que convierte el trabajo real en un activo financiero inmutable (e-OP), facilitando el acceso al crédito productivo, formalizando a las PyMEs y transfiriendo la gobernanza de toda la cadena de valor a la comunidad productiva organizada."*

---

## 📚 Documentación Oficial

Toda la documentación arquitectónica, política y técnica (incluyendo el **Manifiesto Soberano**, el **Dossier del Proyecto de Formalización e Incentivo** y los esquemas de la Mesa de Enlace Sectorial) se encuentra publicada de manera interactiva en nuestro portal oficial:

👉 **[Ingresar al Portal Indinopy.ar](https://indinopy.ar/)**

*(El código fuente de la página web y los documentos Markdown originales se encuentran en la carpeta `/docs/` de este repositorio).*

---

## 🚀 Arquitectura y Stack Tecnológico

Indinopy es un sistema de grado industrial preparado para despliegues SaaS, On-Premise y en topologías federadas (Nodos MES).

- **Backend / Core**: Python 3.12+, Django 6.1 (Server Side Rendering - MVT + REST API).
- **Servidor Web / ASGI**: **Uvicorn** (producción y desarrollo asíncrono de alto rendimiento sobre `core.asgi:application`).
- **Base de Datos**: PostgreSQL + PostGIS (requerido para los campos geoespaciales de auditoría y catastro).
- **Inventario**: Motor de **partida doble** con ubicaciones físicas/virtuales, Quants en tiempo real, reservas JiT y remitos.
- **Manufactura**: Fichas Técnicas (BOM), **Órdenes de Producción Electrónicas (e-OP)** con firma criptográfica Ed25519 y SHA-256, tracking por etapas e hitos por Escrow.
- **Fiscal y Facturación**: Facturación electrónica AFIP/ARCA nativa (Facturas A, B, C, FCE MiPyME Ley 27.440, Notas de Crédito, Notas de Débito, Libro IVA Digital, Convenio Multilateral CM05 y CM03).
- **Omnicanalidad**: Dominio de ventas canónico (`apps.ventas`) desacoplado de canales externos vía adaptadores satélites (`apps.integraciones.woocommerce`).
- **Asincronismo**: Celery + Redis para procesamiento en segundo plano (ingesta de webhooks, Timelocks de gobernanza y sincronización AFIP).
- **Contabilidad**: Asientos automáticos por partida doble vinculando compras, ventas, retenciones provinciales/nacionales y tesorería.

---

## 📁 Módulos del Sistema (`apps/`)

El sistema está dividido en módulos atómicos desacoplados:

```text
indinopy/
├── apps/
│   ├── base/                  # ConfiguracionEmpresa (Singleton) y DocumentoFirmableMixin
│   ├── afip/                  # Facturación electrónica AFIP/ARCA, QR oficial y padrón WSSR
│   ├── mes/                   # Portal Fiduciario, Comisiones, PTF y Gobernanza FIMCA
│   ├── eop/                   # Contrato e-OP Federado, Escrow, Timelock 48h y firmas Ed25519
│   ├── federacion/            # API Gateway, Contratos OpenAPI y Networking mTLS
│   ├── documentos/            # Gestor de adjuntos, firmas criptográficas y Hash SHA-256
│   ├── contactos/             # Libreta unificada (Clientes, Talleristas, CUIT, Condición IVA)
│   ├── inventario/            # Stock por partida doble, Quants, Reservas JiT y Remitos
│   ├── produccion/            # Recetas (BOM), tracking de avance físico y rendimientos
│   ├── contabilidad/          # Plan de cuentas, Libro Diario, Libro Mayor, Libro IVA, CM05/CM03
│   ├── tesoreria/             # Cajas duales, títulos ejecutivos FCE (Ley 27.440), cobros y pagos
│   ├── compras/               # Órdenes de compra y recepción física de insumos
│   ├── nomina/                # Aportes patronales FDI, Sindicato y recursos humanos
│   ├── ventas/                # Core comercial canónico, órdenes agnósticas (DTO) y remitos
│   └── integraciones/
│       └── woocommerce/       # Adaptador satélite multitienda (Webhooks HMAC, polling y sync)
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

# Redis / Celery (Opcional en desarrollo local simple)
REDIS_URL=redis://127.0.0.1:6379/0
```

---

## 🛠️ Instalación y Puesta en Marcha (Recomendado: `uv`)

Indinopy utiliza [`uv`](https://docs.astral.sh/uv/) (el gestor ultrarrápido de paquetes en Rust) para manejar el entorno y dependencias.

### 1. Preparar el Sistema Operativo
Instalá las dependencias de sistema (PostgreSQL, PostGIS, GDAL, compiladores) ejecutando el script incluido:
```bash
chmod +x install.sh
./install.sh
```

### 2. Instalar `uv` y Dependencias
Si aún no tenés `uv` en tu sistema, podés instalarlo con:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Luego sincronizá e incorporá dependencias:
```bash
# Sincronizar el entorno virtual
uv sync

# Si necesitás agregar o actualizar el servidor ASGI Uvicorn:
uv add "uvicorn[standard]"
```

### 3. Inicializar la Base de Datos y Correr con Uvicorn
Usá `uv run` para ejecutar comandos directamente en el entorno aislado del proyecto:
```bash
# Aplicar migraciones
uv run python manage.py makemigrations
uv run python manage.py migrate

# Iniciar servidor ASGI con Uvicorn (Recomendado)
uv run uvicorn core.asgi:application --reload --host 127.0.0.1 --port 8000

# O de modo alternativo con Django runserver
uv run python manage.py runserver
```

---

## 🐳 Despliegue con Docker & Docker Compose

El proyecto incluye un entorno completo en contenedores con **PostgreSQL + PostGIS 16**, **Redis 7**, **Uvicorn ASGI**, **Celery Worker** y **Celery Beat**:

```bash
# 1. Construir y levantar todo el stack (DB, Redis, Uvicorn, Celery)
docker compose up -d --build

# 2. Aplicar migraciones dentro del contenedor
docker compose exec web python manage.py migrate

# 3. Crear superusuario administrativo
docker compose exec web python manage.py createsuperuser

# 4. Ver logs en tiempo real
docker compose logs -f web
```

El servidor web estará disponible inmediatamente en `http://localhost:8000`.

---
*Desarrollado en el territorio fabril del Conurbano Bonaerense para las Organizaciones Libres del Pueblo.*
