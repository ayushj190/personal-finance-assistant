import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DEMO = os.environ.get("PFA_DEMO") == "1"
DB_PATH = DATA_DIR / ("demo.db" if DEMO else "finance.db")
VAULT_PATH = None if DEMO else (DATA_DIR / "vault.bin")
IMPORTS_DIR = DATA_DIR / "imports"
IMPORTS_DIR.mkdir(parents=True, exist_ok=True)

BASE_CURRENCY = "EUR"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen2.5:7b-instruct"
