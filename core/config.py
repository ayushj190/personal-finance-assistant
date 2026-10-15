import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DESKTOP = os.environ.get("PFA_DESKTOP") == "1"


def get_default_data_dir() -> Path:
    if os.environ.get("PFA_DATA_DIR"):
        return Path(os.environ["PFA_DATA_DIR"])
    if DESKTOP and sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "PersonalFinanceAssistant"
    return BASE_DIR / "data"


DATA_DIR = get_default_data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)

DEMO = os.environ.get("PFA_DEMO") == "1"
DB_PATH = DATA_DIR / ("demo.db" if DEMO else "finance.db")
VAULT_PATH = None if DEMO else (DATA_DIR / "vault.bin")
IMPORTS_DIR = DATA_DIR / "imports"
IMPORTS_DIR.mkdir(parents=True, exist_ok=True)

BASE_CURRENCY = "EUR"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen2.5:7b-instruct"
