"""
agent-backend.app.main
-----------------------
FastAPI application entry point for the MemoryBridge agent-backend service.

Responsibilities:
  - Lifespan: start the MCP subprocess on startup, stop it on shutdown.
  - Internal auth middleware: every request must carry a valid HMAC token
    issued by the web service (architecture.md §4.2 — private ALB only).
  - Route registration: /internal/* prefix matches the Fargate private ALB.
  - /health: unauthenticated, for ALB health checks and Docker Compose
    depends_on condition.

Security note:
  In deployment, the agent-backend ALB is internal (not internet-facing).
  The HMAC token check here is a defense-in-depth layer — it ensures that
  even if the internal network were misconfigured, a request without a valid
  signed token would be rejected with 401 (architecture.md §13.1).
"""

import hashlib
import hmac
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware

from .config import get_session_secret
from .mcp_client import mcp_client_context
from .routers import assisted, caregiver, routines

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lifespan — MCP subprocess lifecycle
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the MCP subprocess on startup; stop it on shutdown."""
    async with mcp_client_context() as mcp:
        app.state.mcp = mcp
        logger.info("agent-backend ready — MCP subprocess running.")
        yield
    logger.info("agent-backend shutting down — MCP subprocess stopped.")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="MemoryBridge Agent Backend",
    description="Internal FastAPI service — not directly accessible from the internet.",
    version="0.1.0",
    docs_url=None,          # disable Swagger UI in all environments
    redoc_url=None,         # disable ReDoc in all environments
    openapi_url=None,       # disable OpenAPI schema endpoint
    lifespan=lifespan,
)

# CORS: not needed — this service is called only by the Next.js web service
# on the private Docker network / private ALB, never by a browser directly.


# ---------------------------------------------------------------------------
# Internal auth middleware
# Validates the X-Internal-Token header: HMAC-SHA256(session_id, SESSION_SECRET).
# The web service signs each forwarded request. Any request missing or
# carrying an invalid token is rejected with 401 before routing.
#
# Excluded paths: /health (ALB health check, no token expected).
# ---------------------------------------------------------------------------
EXCLUDED_PATHS = {"/health"}


@app.middleware("http")
async def verify_internal_token(request: Request, call_next):
    if request.url.path in EXCLUDED_PATHS:
        return await call_next(request)

    token = request.headers.get("X-Internal-Token", "")
    session_id = request.headers.get("X-Session-Id", "")

    if not token or not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing internal auth headers.",
        )

    # Compute expected token and compare with a timing-safe digest
    expected = hmac.new(
        get_session_secret().encode(),
        session_id.encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal auth token.",
        )

    return await call_next(request)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
app.include_router(routines.router, prefix="/internal")
app.include_router(caregiver.router, prefix="/internal")
app.include_router(assisted.router,  prefix="/internal")


@app.get("/health", include_in_schema=False)
async def health():
    """ALB health check — unauthenticated, always returns 200 when up."""
    return {"status": "ok"}
