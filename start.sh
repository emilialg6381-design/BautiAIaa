#!/bin/bash
# start.sh — Busca automaticamente la carpeta del proyecto

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# ═══ Encontrar la carpeta del proyecto ═══
# Busca server.py subiendo carpetas desde donde se ejecuto el script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR=""

# 1. Primero chequear donde esta el script
if [ -f "$SCRIPT_DIR/server.py" ]; then
    PROJECT_DIR="$SCRIPT_DIR"
fi

# 2. Si no, buscar en la carpeta actual
if [ -z "$PROJECT_DIR" ] && [ -f "server.py" ]; then
    PROJECT_DIR="$(pwd)"
fi

# 3. Si no, buscar en el directorio padre del script
if [ -z "$PROJECT_DIR" ] && [ -f "$SCRIPT_DIR/../server.py" ]; then
    PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

# 4. Si no, buscar subiendo hasta 5 niveles
if [ -z "$PROJECT_DIR" ]; then
    CHECK_DIR="$(pwd)"
    for i in 1 2 3 4 5; do
        if [ -f "$CHECK_DIR/server.py" ]; then
            PROJECT_DIR="$CHECK_DIR"
            break
        fi
        CHECK_DIR="$(dirname "$CHECK_DIR")"
        [ "$CHECK_DIR" = "/" ] && break
    done
fi

# Si todavia no lo encontro, error
if [ -z "$PROJECT_DIR" ]; then
    echo -e "${RED}No se encontro server.py${NC}"
    echo ""
    echo "Busque en:"
    echo "  - Carpeta actual: $(pwd)"
    echo "  - Donde esta el script: $SCRIPT_DIR"
    echo ""
    echo "Asegurate de estar en la carpeta del proyecto o ejecutar:"
    echo "  cd /ruta/a/tu/proyecto && ./start.sh"
    exit 1
fi

# Ir a la carpeta del proyecto
cd "$PROJECT_DIR"

echo -e "${CYAN}╔══════════════════════════════════════╗${NC}"
echo -e "${CYAN}║      BAUTIAI NEXUS — Gunicorn       ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════╝${NC}"
echo ""
echo -e "Carpeta del proyecto: ${GREEN}$PROJECT_DIR${NC}"
echo ""

# ═══ Verificar archivos ═══
MISSING=""

if [ ! -f "server.py" ]; then
    MISSING="$MISSING\n  - server.py"
fi

if [ ! -f "wsgi.py" ]; then
    MISSING="$MISSING\n  - wsgi.py"
    echo -e "${YELLOW}Creando wsgi.py...${NC}"
    cat > wsgi.py << 'WSGI_EOF'
from server import app
WSGI_EOF
    echo -e "${GREEN}wsgi.py creado${NC}"
fi

if [ ! -f "gunicorn.conf.py" ]; then
    MISSING="$MISSING\n  - gunicorn.conf.py"
    echo -e "${YELLOW}Creando gunicorn.conf.py...${NC}"
    cat > gunicorn.conf.py << 'CONF_EOF'
workers = 1
threads = 8
worker_class = "gthread"
timeout = 0
graceful_timeout = 10
bind = "0.0.0.0:5000"
preload_app = True
accesslog = "-"
errorlog = "-"
loglevel = "info"
proc_name = "bautiai_nexus"
max_requests = 500
max_requests_jitter = 50
daemon = False
pidfile = "gunicorn.pid"

def when_ready(server):
    server.log.info("BautiAI NEXUS listo — http://0.0.0.0:5000")
CONF_EOF
    echo -e "${GREEN}gunicorn.conf.py creado${NC}"
fi

if [ -n "$MISSING" ]; then
    echo -e "${YELLOW}Archivos que faltaban (ya creados):${NC}"
    echo -e "$MISSING"
    echo ""
fi

# ═══ Verificar gunicorn ═══
if ! command -v gunicorn &> /dev/null; then
    echo -e "${RED}Gunicorn no esta instalado.${NC}"
    echo -e "${YELLOW}Ejecuta: pip install gunicorn${NC}"
    exit 1
fi
echo -e "Gunicorn: ${GREEN}$(gunicorn --version)${NC}"

# ═══ Crear directorios ═══
mkdir -p static/images static/videos temp

# ═══ Matar proceso anterior ═══
if [ -f "gunicorn.pid" ]; then
    OLD_PID=$(cat gunicorn.pid 2>/dev/null)
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo -e "${YELLOW}Deteniendo instancia anterior (pid: $OLD_PID)...${NC}"
        kill -TERM "$OLD_PID" 2>/dev/null
        sleep 2
        if kill -0 "$OLD_PID" 2>/dev/null; then
            kill -9 "$OLD_PID" 2>/dev/null
            sleep 1
        fi
    fi
    rm -f gunicorn.pid
fi

# Matar procesos en puerto 5000
OLD_PROC=$(lsof -ti:5000 2>/dev/null)
if [ -n "$OLD_PROC" ]; then
    echo -e "${YELLOW}Liberando puerto 5000...${NC}"
    kill -9 $OLD_PROC 2>/dev/null
    sleep 1
fi

# ═══ Listar archivos ═══
echo ""
echo -e "Archivos encontrados:"
for f in server.py wsgi.py gunicorn.conf.py; do
    if [ -f "$f" ]; then
        SIZE=$(wc -c < "$f")
        echo -e "  ${GREEN}✓${NC} $f (${SIZE} bytes)"
    else
        echo -e "  ${RED}✗${NC} $f"
    fi
done

echo ""
echo -e "${GREEN}Iniciando BautiAI NEXUS...${NC}"
echo -e "${CYAN}Presiona Ctrl+C para detener${NC}"
echo ""

# ═══ Iniciar Gunicorn ═══
exec gunicorn wsgi:app \
    -c gunicorn.conf.py \
    "$@"