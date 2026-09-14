# agent-backend/Dockerfile
# Multi-stage build: builder → runner
# Bundles both agent-backend (FastAPI) and mcp-server (subprocess) in one image,
# matching the "local MCP subprocess inside the backend boundary" architecture
# (implementation.md §12.1).

# ---- Stage 1: Build / install Python deps ----
FROM python:3.12-slim AS builder
WORKDIR /build

# Install build tools for packages that need compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
 && rm -rf /var/lib/apt/lists/*

# Copy and install agent-backend deps
COPY agent-backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Copy and install mcp-server deps
COPY mcp-server/requirements.txt ./mcp-requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r mcp-requirements.txt

# ---- Stage 2: Production runner ----
FROM python:3.12-slim AS runner
WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=8000
EXPOSE 8000

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY agent-backend/app ./app
COPY mcp-server/memorybridge_mcp ./memorybridge_mcp

# Run as non-root
RUN groupadd --system --gid 1001 appgroup \
 && useradd  --system --uid 1001 --gid appgroup appuser
USER appuser

# The MCP subprocess (memorybridge_mcp.server) is launched by the FastAPI
# lifespan handler at startup via StdioServerParameters — not separately here.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
