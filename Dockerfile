# ──────────────────────────────────────────────────────────────────────
#  NeuroSight  –  Production Dockerfile  (repo root)
#  Build context = repo root so we can copy backend/, templates/, static/
# ──────────────────────────────────────────────────────────────────────

# ════════════════════════════════════════════════════════
#  Stage 1: builder  –  install all Python dependencies
# ════════════════════════════════════════════════════════
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY backend/requirements.txt .

RUN pip install --upgrade pip \
 && pip install --no-cache-dir --prefix=/install -r requirements.txt


# ════════════════════════════════════════════════════════
#  Stage 2: runtime  –  minimal final image
# ════════════════════════════════════════════════════════
FROM python:3.11-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

RUN useradd --create-home --shell /bin/bash appuser

# Backend code → /app  (main.py runs from here)
WORKDIR /app
COPY backend/ /app/

# Templates + static one level above /app so main.py's
# Path(__file__).parent.parent / "templates" resolves to /templates
COPY templates/ /templates/
COPY static/ /static/

RUN chown -R appuser:appuser /app /templates /static

USER appuser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" \
    || exit 1

# Railway injects $PORT; fall back to 8000 for other platforms
# --workers 1: the auto-retrain scheduler runs in-process at startup (see main.py
# lifespan). Multiple workers would each start their own scheduler and race to
# retrain/write the same model files concurrently.
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers
