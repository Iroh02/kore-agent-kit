"""Central config. Everything comes from env vars so you can repoint at
whatever provider the organisers hand you, without touching code."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", ROOT / "data"))
INDEX_PATH = ROOT / ".index.json"


def _load_dotenv():
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()

# Any OpenAI-compatible endpoint works: OpenAI, Azure, Groq, Together,
# Fireworks, OpenRouter, vLLM, Ollama (http://localhost:11434/v1).
API_KEY = os.getenv("LLM_API_KEY", "")
BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))
TIMEOUT = int(os.getenv("LLM_TIMEOUT", "60"))
MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "6"))
PORT = int(os.getenv("PORT", "8000"))

# No key -> mock provider. The whole app still runs: retrieval is real,
# only the wording of the final answer is canned. Your demo cannot die.
PROVIDER = "mock" if not API_KEY else "live"
