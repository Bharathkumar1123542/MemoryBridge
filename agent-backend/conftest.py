# agent-backend/conftest.py
# pytest configuration — adds the agent-backend directory to sys.path so
# that `from app.gate.gate import ...` resolves correctly when tests are run
# from the agent-backend/ directory.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
