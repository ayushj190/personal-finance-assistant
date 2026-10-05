import hashlib
import re

PROCESSOR_PREFIXES = re.compile(
    r"^(SUMUP\s*\*|CCV\*|ZETTLE_\*|SQ\s*\*|PAYPAL\s*\*|STICHTING\s+MOLLIE\s+PAYMENTS|MOLLIE\s*\*|"
    r"ADYEN\s*(N\.?V\.?)?|BUCKAROO|STRIPE\s*\*|BEA,?\s*(APPLE|GOOGLE)\s*PAY|GEA,?\s*|BEA,?\s*)\s*",
    re.IGNORECASE,
)

CITIES_PATTERN = (
    r"(SAN\s+FRANCISCO|NEW\s+YORK|DEN\s+HAAG|THE\s+HAGUE|"
    r"AMSTERDAM|ROTTERDAM|UTRECHT|ZAANDAM|HOOFDDORP|EINDHOVEN|GRONINGEN|"
    r"PARIS|LONDON|BERLIN|LUXEMBOURG)"
)
COUNTRY_PATTERN = r"(NLD|NL|DEU|BEL|BE|FRA|FR|GBR|GB|IRL|IE|LUX|LU|USA|US)"

LOCATION_SUFFIX = re.compile(
    rf"\s+({CITIES_PATTERN}\s+)?{COUNTRY_PATTERN}\s*$|\s+{CITIES_PATTERN}\s*$",
    re.IGNORECASE,
)

NOISE_PATTERNS = [
    re.compile(r"\b(NR|PAS|TERM(INAL)?)[:\s]*[A-Z0-9]+", re.IGNORECASE),
    re.compile(r"(\b\d{4}[.\-/]\d{2}[.\-/]\d{2}|\b\d{2}[.\-/]\d{2}[.\-/]\d{2,4})(\s*\d{2}[:.]\d{2}(:\d{2})?)?"),
    re.compile(r"\bLOC\s*\d+\b", re.IGNORECASE),
    re.compile(r"\b\d{4,}\b"),
    re.compile(r"[*#/_\\|]+"),
    re.compile(r"\bIBAN\s*:?\s*[A-Z0-9]{14,34}\b", re.IGNORECASE),
    re.compile(r"\bBIC\s*:?\s*[A-Z0-9]{8,11}\b", re.IGNORECASE),
    re.compile(r"\bSEPA\s+((DIRECT\s+)?DEBIT|CREDIT\s+TRANSFER|OVERBOEKING)?\b", re.IGNORECASE),
    re.compile(r"\bMANDATE(REF)?\s*:?\s*[A-Z0-9-]+\b", re.IGNORECASE),
    re.compile(r"\b(CREDITOR)?(ID|REF)\s*:?\s*[A-Z0-9-]+\b", re.IGNORECASE),
    re.compile(r"\bKENMERK\s*:?\s*[A-Z0-9-]+\b", re.IGNORECASE),
]

TRANSFER_KEYWORDS = re.compile(
    r"\b(top-?up|revolut|trade\s*republic|trading\s*republic|trbk|etoro|spaarrekening|"
    r"savings\s*account|overboeking\s*naar\s*spaarrekening|naar\s*betaalrekening|"
    r"eigen\s*rekening|internal\s*transfer|trading\s*platform\s*wdl|"
    r"trading\s*platform\s*dep|brokerage|ayush\s*kumar\s*joshi|ayush\s*joshi)\b",
    re.IGNORECASE,
)


def clean_merchant(raw: str) -> str:
    if not raw:
        return ""
    text = raw.strip()

    # Extract name from SEPA formatted strings if present
    sepa_naam = re.search(
        r"Naam:\s*([^,;\n]+?)(?:\s+(?:Machtiging|Omschrijving|IBAN|BIC|Kenmerk|$))",
        text,
        re.IGNORECASE,
    )
    if sepa_naam:
        text = sepa_naam.group(1).strip()

    text = PROCESSOR_PREFIXES.sub("", text)
    for pat in NOISE_PATTERNS:
        text = pat.sub(" ", text)

    text = re.sub(r"\s+", " ", text).strip()
    text = LOCATION_SUFFIX.sub("", text).strip()

    # Title case words
    cleaned = text.title()
    return cleaned


def dedup_hash(
    booking_date: str,
    amount_minor: int,
    currency: str,
    description: str,
    occurrence_idx: int = 0,
    external_ref: str | None = None,
) -> str:
    if external_ref and external_ref.strip():
        payload = f"ref|{external_ref.strip()}"
    else:
        norm_desc = clean_merchant(description)
        payload = f"{booking_date}|{amount_minor}|{currency}|{norm_desc}|{occurrence_idx}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def detect_internal_transfer(
    description: str,
    counterparty_name: str | None = None,
    counterparty_iban: str | None = None,
    own_ibans: set[str] | None = None,
) -> bool:
    if counterparty_iban and own_ibans:
        clean_iban = counterparty_iban.replace(" ", "").upper()
        if clean_iban in own_ibans:
            return True

    text_to_check = f"{description} {counterparty_name or ''}"
    if TRANSFER_KEYWORDS.search(text_to_check):
        return True

    return False
