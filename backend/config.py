"""Central configuration. Secrets come only from environment variables / .env."""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

FIRMS_MAP_KEY = os.getenv("FIRMS_MAP_KEY", "").strip()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6").strip()
CESIUM_ION_TOKEN = os.getenv("CESIUM_ION_TOKEN", "").strip()
HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
CACHE_DIR = ROOT / os.getenv("CACHE_DIR", ".cache")
CACHE_DIR.mkdir(exist_ok=True)
REPORTS_DIR = ROOT / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

USER_AGENT = "TerraTrendAI/0.1 (environmental research platform; contact: local-deployment)"
