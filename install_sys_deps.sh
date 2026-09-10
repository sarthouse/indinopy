#!/bin/bash

# ==============================================================================
# Indinopy ERP/MES - Instalador de dependencias del sistema operativo
# ==============================================================================
# Este script detecta la distribución de Linux e instala las librerías
# de C/C++ y bases de datos requeridas (PostgreSQL, PostGIS, GDAL).
# ==============================================================================

set -e # Detener la ejecución si hay algún error

# Detectar el sistema operativo
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
    OS_LIKE=$ID_LIKE
else
    echo "❌ No se pudo detectar el sistema operativo."
    exit 1
fi

echo "🔍 Sistema operativo detectado: $OS ($OS_LIKE)"

# Función para Debian/Ubuntu
install_debian() {
    echo "📦 Actualizando repositorios APT..."
    sudo apt-get update

    echo "🛠️  Instalando herramientas de compilación..."
    sudo apt-get install -y build-essential python3-dev python3-pip

    echo "🗺️  Instalando dependencias Geoespaciales (GDAL, GEOS, PROJ)..."
    sudo apt-get install -y binutils libproj-dev gdal-bin libgdal-dev libgeos-dev

    echo "🐘 Instalando PostgreSQL y PostGIS..."
    sudo apt-get install -y postgresql postgresql-contrib postgis
}

# Función para Fedora/RHEL/CentOS
install_fedora() {
    echo "📦 Actualizando repositorios DNF..."
    sudo dnf check-update || true

    echo "🛠️  Instalando herramientas de compilación..."
    sudo dnf groupinstall -y "Development Tools"
    sudo dnf install -y python3-devel

    echo "🗺️  Instalando dependencias Geoespaciales (GDAL, GEOS, PROJ)..."
    sudo dnf install -y gdal gdal-devel geos-devel proj-devel

    echo "🐘 Instalando PostgreSQL y PostGIS..."
    sudo dnf install -y postgresql-server postgresql-contrib postgis
    
    # Inicializar Postgres en Fedora/RHEL
    if [ ! -d "/var/lib/pgsql/data/base" ]; then
        echo "Inicializando base de datos PostgreSQL..."
        sudo postgresql-setup --initdb || true
        sudo systemctl enable --now postgresql
    fi
}

# Función para Arch Linux
install_arch() {
    echo "📦 Actualizando repositorios PACMAN..."
    sudo pacman -Sy --noconfirm

    echo "🛠️  Instalando herramientas de compilación..."
    sudo pacman -S --noconfirm base-devel python

    echo "🗺️  Instalando dependencias Geoespaciales (GDAL, GEOS, PROJ)..."
    sudo pacman -S --noconfirm gdal geos proj

    echo "🐘 Instalando PostgreSQL y PostGIS..."
    sudo pacman -S --noconfirm postgresql postgis

    # Inicializar Postgres en Arch
    if [ ! -d "/var/lib/postgres/data/base" ]; then
        echo "Inicializando base de datos PostgreSQL..."
        sudo su - postgres -c "initdb -D /var/lib/postgres/data"
        sudo systemctl enable --now postgresql
    fi
}

# Ejecutar la función correspondiente
if [[ "$OS" == "ubuntu" || "$OS" == "debian" || "$OS_LIKE" == *"debian"* ]]; then
    install_debian
elif [[ "$OS" == "fedora" || "$OS" == "centos" || "$OS" == "rhel" || "$OS_LIKE" == *"fedora"* || "$OS_LIKE" == *"rhel"* ]]; then
    install_fedora
elif [[ "$OS" == "arch" || "$OS_LIKE" == *"arch"* ]]; then
    install_arch
else
    echo "❌ Distribución no soportada automáticamente por este script."
    echo "Por favor, instala PostgreSQL, PostGIS y GDAL manualmente usando tu gestor de paquetes."
    exit 1
fi

echo ""
echo "✅ Dependencias del sistema instaladas correctamente."
echo "=========================================================================="
echo "Siguientes pasos:"
echo "1. Crear el usuario y la base de datos en PostgreSQL:"
echo "   sudo -u postgres psql -c \"CREATE DATABASE indinopy;\""
echo "   sudo -u postgres psql -c \"CREATE USER indinopy_user WITH PASSWORD 'tu_password';\""
echo "   sudo -u postgres psql -c \"GRANT ALL PRIVILEGES ON DATABASE indinopy TO indinopy_user;\""
echo "   sudo -u postgres psql -d indinopy -c \"CREATE EXTENSION postgis;\""
echo ""
echo "2. Instalar las dependencias de Python con uv:"
echo "   uv sync"
echo "=========================================================================="
