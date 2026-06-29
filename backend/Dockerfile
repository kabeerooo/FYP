# ──────────────────────────────────────────────────────────────────────
#  NeuroSight  –  Production Dockerfile
#  Multi-stage build to keep the final image lean.
# ──────────────────────────────────────────────────────────────────────

# ════════════════════════════════════════════════════════
#  Stage 1: builder  –  install all Python dependencies
# ════════════════════════════════════════════════════════
FROM python:3.11-slim AS builder

# System packages needed to compile some wheels (e.g. scipy, numpy)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy only requirements first so Docker can cache this layer
COPY requirements.txt .

RUN pip install --upgrade pip \
 && pip install --no-cache-dir --prefix=/install -r requirements.txt


# ════════════════════════════════════════════════════════
#  Stage 2: runtime  –  minimal final image
# ════════════════════════════════════════════════════════
FROM python:3.11-slim AS runtime

# libgomp1 is required at runtime by TensorFlow / NumPy
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Create a non-root user to run the application
RUN useradd --create-home --shell /bin/bash appuser
WORKDIR /app

# Copy application source
COPY . .

# Set ownership
RUN chown -R appuser:appuser /app
USER appuser

# ── Environment defaults (override via docker-compose or .env) ────────
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=8000

# ── Health-check (Docker will mark the container unhealthy if this fails)
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT}/api/health')" \
    || exit 1

EXPOSE 8000

# ── Startup ───────────────────────────────────────────────────────────
# --workers 2  is safe for 1-2 vCPU hosts; increase for larger machines.
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--proxy-headers"]
