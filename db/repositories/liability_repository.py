import sqlite3
from typing import Any, Optional

from db.models import Liability


class LiabilityRepository:
    @staticmethod
    def row_to_liability(row: sqlite3.Row | dict[str, Any]) -> Liability:
        return Liability(
            id=row["id"],
            name=row["name"],
            loan_type=row["loan_type"],
            original_principal_minor=row["original_principal_minor"],
            start_date=row["start_date"],
            lender=row.get("lender", "ABN AMRO") if isinstance(row, dict) else row["lender"],
            home_value_minor=row.get("home_value_minor") if isinstance(row, dict) else row["home_value_minor"],
            term_months=row.get("term_months", 360) if isinstance(row, dict) else row["term_months"],
            payment_match_pattern=row.get("payment_match_pattern") if isinstance(row, dict) else row["payment_match_pattern"],
            balance_override_minor=row.get("balance_override_minor") if isinstance(row, dict) else row["balance_override_minor"],
            balance_override_date=row.get("balance_override_date") if isinstance(row, dict) else row["balance_override_date"],
        )

    @classmethod
    def get_all_liabilities(cls, conn: sqlite3.Connection) -> list[Liability]:
        cur = conn.execute("SELECT * FROM liabilities ORDER BY id ASC")
        return [cls.row_to_liability(r) for r in cur.fetchall()]

    @classmethod
    def get_by_id(cls, conn: sqlite3.Connection, liability_id: int) -> Optional[Liability]:
        cur = conn.execute("SELECT * FROM liabilities WHERE id = ?", (liability_id,))
        row = cur.fetchone()
        return cls.row_to_liability(row) if row else None

    @staticmethod
    def get_schedule(conn: sqlite3.Connection, liability_id: int) -> list[dict[str, Any]]:
        cur = conn.execute(
            """
            SELECT * FROM liability_schedule
            WHERE liability_id = ?
            ORDER BY month_idx ASC
            """,
            (liability_id,),
        )
        return [dict(r) for r in cur.fetchall()]

    @staticmethod
    def get_rate_periods(conn: sqlite3.Connection, liability_id: int) -> list[dict[str, Any]]:
        cur = conn.execute(
            """
            SELECT * FROM liability_rate_periods
            WHERE liability_id = ?
            ORDER BY from_date ASC
            """,
            (liability_id,),
        )
        return [dict(r) for r in cur.fetchall()]

    @staticmethod
    def get_extra_payments(conn: sqlite3.Connection, liability_id: int) -> list[dict[str, Any]]:
        cur = conn.execute(
            """
            SELECT * FROM liability_extra_payments
            WHERE liability_id = ?
            ORDER BY paid_date ASC
            """,
            (liability_id,),
        )
        return [dict(r) for r in cur.fetchall()]
