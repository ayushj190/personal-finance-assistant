from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "finance.db"
VAULT_PATH = DATA_DIR / "vault.bin"
IMPORTS_DIR = DATA_DIR / "imports"
IMPORTS_DIR.mkdir(parents=True, exist_ok=True)

BASE_CURRENCY = "EUR"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen2.5-coder:7b"
