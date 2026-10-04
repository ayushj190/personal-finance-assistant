import json
from pathlib import Path
from cryptography.fernet import Fernet
import keyring

from config import DATA_DIR, VAULT_PATH

SERVICE_NAME = "personal_finance_assistant"
VAULT_KEY_NAME = "vault_master_key"
FALLBACK_KEY_FILE = DATA_DIR / ".vault_master.key"


def _get_or_create_master_key() -> bytes:
    key_str = None
    try:
        key_str = keyring.get_password(SERVICE_NAME, VAULT_KEY_NAME)
    except Exception:
        pass

    if not key_str and FALLBACK_KEY_FILE.exists():
        try:
            key_str = FALLBACK_KEY_FILE.read_text(encoding="utf-8").strip()
        except Exception:
            pass

    if not key_str:
        key_bytes = Fernet.generate_key()
        key_str = key_bytes.decode("utf-8")
        try:
            keyring.set_password(SERVICE_NAME, VAULT_KEY_NAME, key_str)
        except Exception:
            FALLBACK_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
            FALLBACK_KEY_FILE.write_text(key_str, encoding="utf-8")
        return key_bytes

    return key_str.encode("utf-8")


def _read_vault(vault_path: Path = VAULT_PATH) -> dict[str, str]:
    if not vault_path.exists():
        return {}
    fernet = Fernet(_get_or_create_master_key())
    try:
        encrypted_data = vault_path.read_bytes()
        decrypted_data = fernet.decrypt(encrypted_data)
        return json.loads(decrypted_data.decode("utf-8"))
    except Exception:
        return {}


def _write_vault(data: dict[str, str], vault_path: Path = VAULT_PATH) -> None:
    vault_path.parent.mkdir(parents=True, exist_ok=True)
    fernet = Fernet(_get_or_create_master_key())
    encrypted_data = fernet.encrypt(json.dumps(data).encode("utf-8"))
    vault_path.write_bytes(encrypted_data)


def get(name: str, vault_path: Path = VAULT_PATH) -> str | None:
    data = _read_vault(vault_path)
    return data.get(name)


def put(name: str, value: str, vault_path: Path = VAULT_PATH) -> None:
    data = _read_vault(vault_path)
    data[name] = value
    _write_vault(data, vault_path)


def delete(name: str, vault_path: Path = VAULT_PATH) -> None:
    data = _read_vault(vault_path)
    if name in data:
        del data[name]
        _write_vault(data, vault_path)


def list_keys(vault_path: Path = VAULT_PATH) -> list[str]:
    data = _read_vault(vault_path)
    return list(data.keys())
