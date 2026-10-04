from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import time
from typing import Any
import uuid
import httpx
import jwt

from connectors.base import NeedsReauth, RawAccount, RawTransaction
from connectors.file_import.csv_profiles import to_minor
from services import secrets_vault

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

BASE_URL = "https://api.enablebanking.com"


def generate_rsa_keypair() -> tuple[str, str]:
    """Generates a 2048-bit RSA private and public key pair in PEM format."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_pem, public_pem


class EnableBankingService:
    def __init__(self, session_vault_key: str = "eb_session_id") -> None:
        self.session_vault_key = session_vault_key

    def is_configured(self) -> bool:
        app_id = secrets_vault.get("eb_app_id")
        key_pem = secrets_vault.get("eb_key_pem")
        return bool(app_id and key_pem)

    def _generate_jwt(self) -> str:
        app_id = secrets_vault.get("eb_app_id")
        key_pem = secrets_vault.get("eb_key_pem")
        if not app_id or not key_pem:
            raise ValueError("Enable Banking app_id or private key not configured.")

        now = int(time.time())
        payload = {
            "iss": "enablebanking.com",
            "aud": "api.enablebanking.com",
            "iat": now,
            "exp": now + 3600,
        }
        headers = {"kid": app_id, "alg": "RS256"}
        return jwt.encode(payload, key_pem, algorithm="RS256", headers=headers)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._generate_jwt()}",
            "Content-Type": "application/json",
        }

    def start_auth(self, aspsp_name: str, country: str = "NL", redirect_url: str = "https://localhost:8501/") -> str:
        valid_until = (datetime.now(timezone.utc) + timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
        state = str(uuid.uuid4())
        payload = {
            "access": {"valid_until": valid_until},
            "aspsp": {"name": aspsp_name, "country": country},
            "state": state,
            "redirect_url": redirect_url,
            "psu_type": "personal",
        }
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(f"{BASE_URL}/auth", json=payload, headers=self._headers())
            if resp.status_code >= 400:
                err_text = resp.text
                if "WRONG_ASPSP_PROVIDED" in err_text:
                    raise RuntimeError(
                        f"Bank '{aspsp_name}' ({country}) is not available in your Enable Banking environment. "
                        f"In SANDBOX mode, live banks (ABN AMRO, ING, etc.) cannot be accessed directly; "
                        f"use 'Mock ASPSP' or Rabobank for testing. For live accounts, a PRODUCTION app is required."
                    )
                raise RuntimeError(f"Enable Banking auth start failed: {err_text}")
            data = resp.json()
            return data["url"]

    def get_aspsps(self, country: str | None = None) -> list[dict[str, Any]]:
        params = {"country": country} if country else {}
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(f"{BASE_URL}/aspsps", params=params, headers=self._headers())
            if resp.status_code >= 400:
                return []
            return resp.json().get("aspsps", [])

    def complete_auth(self, code: str) -> dict[str, Any]:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(f"{BASE_URL}/sessions", json={"code": code}, headers=self._headers())
            if resp.status_code >= 400:
                raise RuntimeError(f"Enable Banking complete auth failed: {resp.text}")
            data = resp.json()
            session_id = data.get("session_id")
            if session_id:
                secrets_vault.put(self.session_vault_key, session_id)
                if "access" in data and "valid_until" in data["access"]:
                    secrets_vault.put(f"{self.session_vault_key}_valid_until", data["access"]["valid_until"])
            return data

    def fetch_accounts(self) -> list[RawAccount]:
        session_id = secrets_vault.get(self.session_vault_key)
        if not session_id:
            raise NeedsReauth("No active Enable Banking session found.")

        with httpx.Client(timeout=30.0) as client:
            resp = client.get(f"{BASE_URL}/sessions/{session_id}", headers=self._headers())
            if resp.status_code in (401, 403, 404):
                raise NeedsReauth(f"Session expired or invalid: {resp.status_code}")
            if resp.status_code >= 400:
                raise RuntimeError(f"Failed to fetch accounts: {resp.text}")

            data = resp.json()
            accounts_data = data.get("accounts", [])
            aspsp = data.get("aspsp", {})
            institution = aspsp.get("name", "Bank")

            result: list[RawAccount] = []
            for acc in accounts_data:
                uid = acc.get("uid") or acc.get("account_id", {}).get("iban")
                iban = acc.get("account_id", {}).get("iban")
                currency = acc.get("currency", "EUR")

                # Fetch balances
                bal_minor = None
                try:
                    b_resp = client.get(f"{BASE_URL}/accounts/{uid}/balances", headers=self._headers())
                    if b_resp.status_code == 200:
                        b_data = b_resp.json()
                        for b in b_data.get("balances", []):
                            amt = b.get("balance_amount", {}).get("amount")
                            if amt is not None:
                                bal_minor = to_minor(amt)
                                break
                except Exception:
                    pass

                result.append(
                    RawAccount(
                        external_id=str(uid),
                        institution=institution,
                        name=f"{institution} ({iban[-4:] if iban else 'Account'})",
                        currency=currency,
                        asset_class="cash",
                        iban=iban,
                        balance_minor=bal_minor,
                    )
                )
            return result

    def fetch_transactions(self, since: date) -> list[RawTransaction]:
        accounts = self.fetch_accounts()
        raw_txs: list[RawTransaction] = []

        with httpx.Client(timeout=30.0) as client:
            for acc in accounts:
                url = f"{BASE_URL}/accounts/{acc.external_id}/transactions"
                params: dict[str, Any] = {"date_from": since.isoformat()}
                while True:
                    resp = client.get(url, params=params, headers=self._headers())
                    if resp.status_code in (401, 403):
                        raise NeedsReauth("Enable Banking session authorization expired.")
                    if resp.status_code >= 400:
                        break

                    data = resp.json()
                    for entry in data.get("transactions", []):
                        amt_info = entry.get("transaction_amount", {})
                        amt_val = amt_info.get("amount", "0")
                        curr = amt_info.get("currency", acc.currency)
                        amt_minor = to_minor(amt_val)

                        indicator = entry.get("credit_debit_indicator", "CRDT").upper()
                        if indicator == "DBIT" and amt_minor > 0:
                            amt_minor = -amt_minor
                        elif indicator == "CRDT" and amt_minor < 0:
                            amt_minor = -amt_minor

                        b_date_str = entry.get("booking_date") or entry.get("value_date")
                        if not b_date_str:
                            continue
                        booking_date = datetime.strptime(b_date_str[:10], "%Y-%m-%d").date()

                        desc_list = entry.get("remittance_information", [])
                        desc = " ".join(desc_list) if desc_list else entry.get("entry_reference", "Transaction")

                        cdtr = entry.get("creditor", {}).get("name")
                        dbtr = entry.get("debtor", {}).get("name")
                        cp_name = cdtr if indicator == "DBIT" else dbtr

                        raw_txs.append(
                            RawTransaction(
                                account_external_id=acc.external_id,
                                booking_date=booking_date,
                                amount_minor=amt_minor,
                                currency=curr,
                                description=desc,
                                external_ref=entry.get("entry_reference"),
                                counterparty_name=cp_name,
                                mcc=entry.get("merchant_category_code"),
                            )
                        )

                    continuation_key = data.get("continuation_key")
                    if continuation_key:
                        params["continuation_key"] = continuation_key
                    else:
                        break

        return raw_txs

    def fetch_holdings(self) -> list:
        return []
