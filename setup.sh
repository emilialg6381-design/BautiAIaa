#!/bin/bash

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}╔════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║  🎬 BautiAI NEXUS - Setup Helper      ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════╝${NC}"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 no encontrado${NC}"
    echo "Descarga Python desde: https://www.python.org/"
    exit 1
fi
echo -e "${GREEN}✓${NC} Python encontrado: $(python3 --version)"

# Check if venv exists
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}📦 Creando virtual environment...${NC}"
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate 2>/dev/null || . venv/Scripts/activate 2>/dev/null
echo -e "${GREEN}✓${NC} Virtual environment activado"

# Install dependencies
echo -e "${YELLOW}📥 Instalando dependencias...${NC}"
pip install --no-cache-dir -r requirements.txt --break-system-packages 2>/dev/null
echo -e "${GREEN}✓${NC} Dependencias instaladas"

# Install Playwright
echo -e "${YELLOW}🎭 Instalando Playwright...${NC}"
python -m playwright install chromium 2>/dev/null
echo -e "${GREEN}✓${NC} Playwright listo"

# Create directories
mkdir -p templates static/images static/videos
echo -e "${GREEN}✓${NC} Directorios creados"

# Move index.html if needed
if [ -f "index.html" ] && [ ! -f "templates/index.html" ]; then
    mv index.html templates/
    echo -e "${GREEN}✓${NC} index.html movido a templates/"
fi

echo ""
echo -e "${CYAN}════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ Setup completado!${NC}"
echo -e "${CYAN}════════════════════════════════════════${NC}"
echo ""
echo -e "Para iniciar la aplicación:"
echo -e "  ${CYAN}python server.py${NC}"
echo ""
echo -e "O con Gunicorn:"
echo -e "  ${CYAN}gunicorn wsgi:app -c gunicorn.conf.py${NC}"
echo ""
echo -e "Acceder en: ${CYAN}http://localhost:5000${NC}"
echo ""
