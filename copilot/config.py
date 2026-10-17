"""Runtime settings, read from the environment (and an optional .env file)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv():
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
MODEL = os.environ.get("COPILOT_MODEL", "google/gemma-4-31b-it:free")
FALLBACK_MODELS = [m.strip() for m in os.environ.get(
    "COPILOT_FALLBACK_MODELS", "google/gemma-4-26b-a4b-it:free").split(",") if m.strip()]
DATA_DIRS = [d.strip() for d in os.environ.get(
    "COPILOT_DATA_DIRS", "data/flytbase-dataset/sample-data").split(",") if d.strip()]
AS_OF = os.environ.get("COPILOT_AS_OF", "").strip() or None
DEFAULT_PASSWORD = os.environ.get("COPILOT_DEFAULT_PASSWORD", "flytbase2026")
DB_PATH = os.environ.get("COPILOT_DB", str(ROOT / "copilot.db"))
MAX_AGENT_STEPS = int(os.environ.get("COPILOT_MAX_STEPS", "8"))


def resolve_dir(d: str) -> Path:
    p = Path(d)
    if not p.is_absolute():
        p = ROOT / p
    # Accept either the dataset repo root or its sample-data folder
    if (p / "sample-data").is_dir() and not (p / "assets").is_dir():
        p = p / "sample-data"
    return p
