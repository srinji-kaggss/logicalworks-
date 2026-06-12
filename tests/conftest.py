"""Pytest configuration — ensure repo root is on sys.path for imports."""
import sys
from pathlib import Path

# Add repo root to path so lgwks_* modules resolve correctly
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
