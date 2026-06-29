#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────
#  NeuroSight  –  deploy.sh
#  One-command production deployment via Docker Compose
#
#  USAGE
#  -----
#    chmod +x backend/deploy.sh
#    ./backend/deploy.sh [--pull] [--seed-admin]
#
#  FLAGS
#  -----
#    --pull         Pull the latest image from Docker Hub before deploying
#    --seed-admin   Run create_admin.py after deployment to create the
#                   first admin account (only needed on a fresh install)
#
#  PREREQUISITES
#  -------------
#    • Docker + Docker Compose installed
#    • A  .env  file in the project root with all required API keys
#    • backend/firebase-service-account.json present
# ──────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── colour helpers ────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'   # no colour

info()  { echo -e "${GREEN}[deploy]${NC} $*"; }
warn()  { echo -e "${YELLOW}[deploy]${NC} $*"; }
error() { echo -e "${RED}[deploy]${NC} $*" >&2; exit 1; }

# ── resolve project root (one level above backend/) ──────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"
cd "${PROJECT_ROOT}"

# ── parse flags ───────────────────────────────────────────────────────
DO_PULL=false
SEED_ADMIN=false

for arg in "$@"; do
    case "${arg}" in
        --pull)       DO_PULL=true    ;;
        --seed-admin) SEED_ADMIN=true ;;
        *) warn "Unknown flag: ${arg}" ;;
    esac
done

# ── pre-flight checks ─────────────────────────────────────────────────
info "Running pre-flight checks..."

command -v docker         >/dev/null 2>&1 || error "Docker is not installed."
command -v docker-compose >/dev/null 2>&1 || docker compose version >/dev/null 2>&1 \
    || error "Docker Compose is not installed."

[[ -f ".env" ]] || {
    warn ".env file not found. Creating from .env.example if available..."
    [[ -f ".env.example" ]] && cp .env.example .env \
        || warn "No .env.example found. Proceeding without .env (defaults will be used)."
}

[[ -f "backend/firebase-service-account.json" ]] \
    || error "backend/firebase-service-account.json not found. Deployment aborted."

# ── pull latest image (optional) ─────────────────────────────────────
if [[ "${DO_PULL}" == "true" ]]; then
    info "Pulling latest images..."
    docker-compose pull api 2>/dev/null || docker compose pull api
fi

# ── stop existing containers ──────────────────────────────────────────
info "Stopping existing containers..."
docker-compose down --remove-orphans 2>/dev/null \
    || docker compose down --remove-orphans \
    || true

# ── build & start ─────────────────────────────────────────────────────
info "Building and starting services..."
docker-compose up --build -d 2>/dev/null \
    || docker compose up --build -d

# ── wait for health check ─────────────────────────────────────────────
info "Waiting for API to become healthy..."
MAX_RETRIES=20
RETRY_DELAY=5
for i in $(seq 1 ${MAX_RETRIES}); do
    STATUS=$(docker inspect --format="{{.State.Health.Status}}" neurosight_api 2>/dev/null || echo "starting")
    if [[ "${STATUS}" == "healthy" ]]; then
        info "API is healthy! ✓"
        break
    fi
    if [[ $i -eq ${MAX_RETRIES} ]]; then
        warn "API did not report healthy after $((MAX_RETRIES * RETRY_DELAY))s"
        warn "Check logs with:  docker-compose logs api"
    fi
    sleep ${RETRY_DELAY}
done

# ── seed admin account (optional) ─────────────────────────────────────
if [[ "${SEED_ADMIN}" == "true" ]]; then
    info "Seeding admin account..."
    docker-compose exec api python create_admin.py 2>/dev/null \
        || docker compose exec api python create_admin.py \
        || warn "Admin seeding failed — run it manually inside the container."
fi

# ── done ──────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo -e "${GREEN}  NeuroSight deployed successfully!     ${NC}"
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo ""
echo "  API:          http://localhost:8000"
echo "  Admin panel:  http://localhost:8000/admin_login.html"
echo "  Logs:         docker-compose logs -f api"
echo "  Stop:         docker-compose down"
echo ""
