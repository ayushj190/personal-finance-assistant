from datetime import datetime
from decimal import Decimal
import xml.etree.ElementTree as ET

from connectors.base import RawTransaction
from connectors.file_import.csv_profiles import to_minor


def parse_camt053(xml_text: str, default_account_id: str = "bank_account") -> list[RawTransaction]:
    raw_txs: list[RawTransaction] = []
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return raw_txs

    # Handle XML namespaces dynamically by stripping namespace tags
    def local_name(tag: str) -> str:
        return tag.split("}")[-1] if "}" in tag else tag

    for elem in root.iter():
        elem.tag = local_name(elem.tag)

    for entry in root.findall(".//Ntry"):
        amt_elem = entry.find("Amt")
        if amt_elem is None or not amt_elem.text:
            continue

        currency = amt_elem.attrib.get("Ccy", "EUR")
        amount_minor = to_minor(Decimal(amt_elem.text.strip()))

        indicator = entry.findtext("CdtDbtInd", "DBIT").strip().upper()
        if indicator == "DBIT" and amount_minor > 0:
            amount_minor = -amount_minor
        elif indicator == "CRDT" and amount_minor < 0:
            amount_minor = -amount_minor

        # Booking date
        date_elem = entry.find(".//BookgDt/Dt")
        if date_elem is None or not date_elem.text:
            date_elem = entry.find(".//ValDt/Dt")
        if date_elem is None or not date_elem.text:
            continue

        try:
            booking_date = datetime.strptime(
                date_elem.text.strip()[:10], "%Y-%m-%d").date()
        except ValueError:
            continue

        # Extract counterparty, remittance, and references
        desc_parts: list[str] = []
        ustrd = entry.findall(".//RmtInf/Ustrd")
        for u in ustrd:
            if u.text:
                desc_parts.append(u.text.strip())

        cdtr_nm = entry.findtext(".//RltdPties/Cdtr/Nm")
        dbtr_nm = entry.findtext(".//RltdPties/Dbtr/Nm")
        counterparty = cdtr_nm if indicator == "DBIT" else dbtr_nm
        if counterparty:
            desc_parts.insert(0, counterparty.strip())

        cdtr_iban = entry.findtext(".//RltdPties/CdtrAcct/Id/IBAN")
        dbtr_iban = entry.findtext(".//RltdPties/DbtrAcct/Id/IBAN")
        counterparty_iban = cdtr_iban if indicator == "DBIT" else dbtr_iban

        ref = entry.findtext(
            ".//AcctSvcrRef") or entry.findtext(".//Refs/EndToEndId")

        description = " ".join(desc_parts) if desc_parts else "Bank Transfer"

        raw_txs.append(
            RawTransaction(
                account_external_id=default_account_id,
                booking_date=booking_date,
                amount_minor=amount_minor,
                currency=currency,
                description=description,
                counterparty_name=counterparty,
                counterparty_iban=counterparty_iban,
                external_ref=ref,
            )
        )

    return raw_txs
