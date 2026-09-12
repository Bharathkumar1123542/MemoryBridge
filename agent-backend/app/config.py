"""
agent-backend.app.config
-------------------------
Environment variable loading for the agent-backend service.

ALL configuration that varies between environments lives here.
No other module should call os.environ directly — import from this module.

Environment variables (implementation.md §12.4):
  BEDROCK_MODEL_ID_REASONING  — model for Semantic Safety Reviewer + Communication Agent
  BEDROCK_MODEL_ID_FAST       — model for Routine Planning Agent + Escalation Agent
  AWS_REGION                  — Bedrock and Secrets Manager region
  SESSION_SECRET              — HMAC key for internal service token verification
  INTERNAL_AGENT_BACKEND_PORT — (optional) port agent-backend listens on; default 8000

Note: DATABASE_URL is intentionally NOT loaded here. It exists only in the
MCP subprocess environment (server.py) — FastAPI route handlers and Agent
objects never hold it (architecture.md §1, Principle 4).
"""

import os


def _require(name: str) -> str:
    """Return the value of an environment variable, raising if absent."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Required environment variable '{name}' is not set. "
            f"See implementation.md §12.4 for the full variable reference."
        )
    return value


# ---------------------------------------------------------------------------
# Amazon Bedrock model tiers (architecture.md §12)
# Both default to a Claude 3.5 Sonnet class model; override via env vars to
# upgrade without a code change. The IAM policy in architecture.md §4.4
# scopes InvokeModel to exactly these two configured IDs.
# ---------------------------------------------------------------------------
BEDROCK_MODEL_ID_REASONING: str = os.environ.get(
    "BEDROCK_MODEL_ID_REASONING",
    "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
)

BEDROCK_MODEL_ID_FAST: str = os.environ.get(
    "BEDROCK_MODEL_ID_FAST",
    "us.anthropic.claude-3-haiku-20240307-v1:0",
)

AWS_REGION: str = os.environ.get("AWS_REGION", "us-east-1")

# ---------------------------------------------------------------------------
# Internal auth
# SESSION_SECRET is required at runtime but fetched lazily so test modules
# that don't exercise auth can import config without the var being set.
# ---------------------------------------------------------------------------
def get_session_secret() -> str:
    """Return SESSION_SECRET, raising loudly if not set."""
    return _require("SESSION_SECRET")

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
PORT: int = int(os.environ.get("PORT", "8000"))

# ---------------------------------------------------------------------------
# MCP subprocess command
# The agent-backend image bundles the mcp-server directory so this path
# resolves correctly inside the container (implementation.md §12.1).
# In local dev, ensure mcp-server/ is on PYTHONPATH or installed.
# ---------------------------------------------------------------------------
MCP_SERVER_COMMAND = "python"
MCP_SERVER_ARGS = ["-m", "memorybridge_mcp.server"]
