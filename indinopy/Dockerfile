# ==============================================================================
# Indinopy ERP/MES - Dockerfile de Producción / Desarrollo
# Soporte nativo para Django 6.1 + PostGIS (GDAL/GEOS) + Uvicorn ASGI
# ==============================================================================

FROM python:3.12-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    UV_SYSTEM_PYTHON=1 \
    DEBIAN_FRONTEND=noninteractive

# Instalar dependencias del sistema requeridas para PostGIS, Criptografía (PyNaCl) y C libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    libpq-dev \
    binutils \
    libproj-dev \
    gdal-bin \
    libgdal-dev \
    libgeos-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Instalar uv desde la imagen oficial de Astral
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Copiar archivos de dependencias para aprovechar la caché de Docker
COPY pyproject.toml uv.lock* /app/

# Instalar dependencias del proyecto usando uv
RUN uv pip install --system -r pyproject.toml

# Copiar el código fuente completo del proyecto
COPY . /app/

# Exponer el puerto por defecto de Uvicorn
EXPOSE 8000

# Comando por defecto: ejecutar Uvicorn con ASGI
CMD ["uvicorn", "core.asgi:application", "--host", "0.0.0.0", "--port", "8000"]
