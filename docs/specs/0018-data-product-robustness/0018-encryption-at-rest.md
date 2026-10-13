# Encryption at rest for sensitive identifiers

Part of umbrella spec [0018](index.md). Build spec for one decision.

## Summary

The database file is plaintext today, so a copied `finance.db` exposes who the owner paid. This child encrypts the two sensitive text fields, counterparty IBAN and counterparty name, using the existing Fernet key from the credential vault. Amounts, dates, descriptions and merchant fields stay plaintext so sums, search and categorization keep working. A one time migration encrypts the rows already on disk.

## Requirements

**User stories**:

- As the owner, I want counterparty identities encrypted on disk, so a copied database does not reveal who I paid.

**Acceptance criteria**:

- **AC-1**: `services/crypto.py` provides `encrypt_field` and `decrypt_field` using Fernet with a key resolver over `services/secrets_vault.py` that never creates a new key (a create disabled path), stores a key fingerprint (an HMAC of a constant) and verifies it on read; no second key store is introduced.
- **AC-2**: `transactions.counterparty_iban` and `counterparty_name` are stored encrypted in `counterparty_iban_enc` and `counterparty_name_enc`; the plaintext columns are null after the backfill.
- **AC-3**: A one time data migration encrypts every existing plaintext counterparty value; it is idempotent (a second run encrypts nothing new), is recorded so it never silently re runs, and aborts without recording if the vault key is unavailable.
- **AC-4**: One repository writer owns `transactions` and always writes `*_enc`, decrypting on read back into the `Transaction` dataclass, so all existing readers and the UI are unchanged; the UI still masks them when values are hidden.
- **AC-5**: If the key is unavailable or a token is invalid, reads return `None` plus a `counterparty_unavailable` flag (never an empty string), the failure is cached for about 60 seconds so a large page does not log per row, and the UI shows the field as unavailable rather than raw ciphertext.
- **AC-6**: Amounts, dates, descriptions and merchant fields stay plaintext, so sums, search and categorization keep working.
- **AC-7**: After the backfill, `PRAGMA secure_delete=ON` is set, a WAL checkpoint runs and the database is vacuumed outside the migration transaction, and any index on the plaintext counterparty columns is dropped, so plaintext does not linger in free pages or the WAL.
- **AC-8**: A test writes through every ingest path (connector, file import, manual edit, demo seed) and asserts the plaintext counterparty columns stay null and the ciphertext decrypts back.
- **AC-9**: Every reader of the plaintext counterparty columns is found and updated; if an equality match is needed (transfer matching, recurring detection), an HMAC blind index column is added, and counterparty fields are hidden from the copilot SQL schema prompt.

## Decision

**Chosen option**: field level Fernet on the counterparty identifiers, reusing the vault key, with a one time backfill; SQLCipher is rejected.

**Implementation skills**: none yet.

## Design

**Data**: adds `counterparty_iban_enc` and `counterparty_name_enc` to `transactions`; the plaintext columns are nulled after the backfill but stay in the schema.

**Surface**:

| Function | Where | Inputs | Outputs | Errors |
|---|---|---|---|---|
| `encrypt_field` / `decrypt_field` | `services/crypto.py` | plaintext / token | token / plaintext | key missing, `InvalidToken` |
| `key_fingerprint` | `services/crypto.py` | none | HMAC of a constant | key missing |
| `backfill_counterparty` | `db/migrations/NNNN_encrypt_counterparty.py` | connection | encrypted rows | db or key error |

**Backfill safety**: encrypt into the `*_enc` column first, verify the ciphertext decrypts back to the plaintext, then null the plaintext column, all inside the migration transaction. Run `PRAGMA secure_delete=ON` before nulling, then a WAL checkpoint and a `VACUUM` after the transaction. Abort without recording if the key is unavailable. The migration number is assigned at build time.

**Read path**: one Fernet instance is cached per process and fetched lazily; on failure the failure is cached for about 60 seconds and logged once. The repository returns `None` plus a `counterparty_unavailable` flag; it never returns raw ciphertext.

**Key**: the resolver is create disabled, so a fresh key is never generated silently. A stored fingerprint is verified before decrypting. A vault reset or rotation is documented as making the encrypted fields unrecoverable; the pre migrate backup holds plaintext only until the retention rule ages it out.

**Demo mode**: the demo database uses the same key resolver; when no real key exists the demo seed uses a fixed local demo key, and the ciphertext is throwaway.

**Value sourcing**: the key comes from `services/secrets_vault.py`; the fingerprint is an HMAC of a constant; the masked fallback is the existing privacy behavior.

**Invariants**: identifiers are never stored plaintext after backfill; amounts are never encrypted; a key loss is a loud, non fatal read failure, not silent corruption.

## Build plan

1. Add `services/crypto.py`: the create disabled key resolver, the fingerprint, `encrypt_field` and `decrypt_field`, and the cached Fernet instance. Satisfies **AC-1**
2. Add the `*_enc` columns (part of the shared schema migration). Satisfies **AC-2**
3. Grep and update every reader of the plaintext counterparty columns; add the HMAC blind index if equality is needed, and hide counterparty fields from the copilot schema prompt. Satisfies **AC-9**
4. Write the backfill as a Python data migration (encrypt, verify, null), with `secure_delete`, a WAL checkpoint and a `VACUUM`. Satisfies **AC-3**, **AC-7**
5. Switch the single transaction writer to write `*_enc`, decrypt on read, and keep the privacy masking. Satisfies **AC-4**, **AC-6**
6. Handle the missing or invalid key path with `None` plus the unavailable flag and a once only cached warning, and add the every ingest path test. Satisfies **AC-5**, **AC-8**

## Consequences

**Positive**: a copied database no longer reveals counterparty identities; the query hot path (sums, search) is untouched.

**Negative / tradeoffs**: encrypted fields are not searchable in SQL and need a blind index for equality; a lost key makes those fields unreadable; the backfill is irreversible for the data it touches, and its only recovery is the pre migrate backup, which itself holds plaintext until retention ages it out.

**Neutral**: the database file itself stays plaintext, so OS disk encryption remains the outer layer.

## Follow-up

- [ ] Optional later: extend encryption to any other identifier fields (for example a payee reference) if they are added.
