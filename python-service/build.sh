#!/usr/bin/env bash
# Build script para Render — instala dependencias del sistema para WeasyPrint
# Configurar en Render: Build Command → bash python-service/build.sh
set -e

echo "==> Instalando dependencias del sistema para WeasyPrint..."
apt-get install -y --no-install-recommends \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-liberation \
    fonts-dejavu-core

echo "==> Instalando dependencias Python..."
pip install -r python-service/requirements.txt

echo "==> Build completado."
