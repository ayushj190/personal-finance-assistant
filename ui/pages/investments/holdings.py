import json
from pathlib import Path
from typing import Any, Optional
import pandas as pd
import streamlit as st

import ui.pages.investments
from ui.components import is_hidden


@st.cache_data(ttl=60)
def load_cached_json(file_path: Path) -> Optional[Any]:
    if file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def render_copy_portfolios(copy_df: pd.DataFrame, usd_to_eur: float) -> None:
    cache_path = Path(__file__).resolve().parent.parent.parent.parent / "data" / "etoro_mirrors_cache.json"
    meta_path = Path(__file__).resolve().parent.parent.parent.parent / "data" / "ticker_metadata.json"

    mirrors_data = load_cached_json(cache_path)
    mirrors_map = {m["ticker"]: m for m in mirrors_data} if mirrors_data else {}
    meta_map = load_cached_json(meta_path) or {}

    for _, row in copy_df.iterrows():
        ticker = row["ticker"]
        username = ticker.replace("COPY:", "")
        mirror_info = mirrors_map.get(ticker, {})

        invested_usd = mirror_info.get("invested_usd", float(row["cost_basis"]))
        val_usd = mirror_info.get("value_usd", float(row["value_eur"]) / usd_to_eur)
        pnl_usd = mirror_info.get("unrealized_pnl_usd", val_usd - invested_usd)
        ret_pct = (pnl_usd / invested_usd * 100.0) if invested_usd > 0 else 0.0

        invested_eur = invested_usd * usd_to_eur
        val_eur = val_usd * usd_to_eur
        pnl_eur = pnl_usd * usd_to_eur
        pnl_sign = "+" if pnl_eur >= 0 else ""

        underlying = mirror_info.get("positions", [])
        a_types: dict[str, float] = {}
        total_val = val_usd
        for p in underlying:
            sym = p.get("symbol") or f"ID_{p.get('instrument_id')}"
            m_info = meta_map.get(sym, {})
            a_type = m_info.get("asset_type")
            if not a_type:
                a_type = "etf" if "ETF" in (p.get("name") or "").upper() else "stock"
            p_val = float(p.get("amount_usd", 0.0)) + float(p.get("pnl_usd", 0.0))
            a_types[a_type] = a_types.get(a_type, 0.0) + p_val

        breakdown_str = " | ".join(
            [f"{k.upper()}: {(v / total_val * 100):.1f}%" for k, v in a_types.items() if total_val > 0]
        )

        if ui.pages.investments.is_hidden():
            label = f"👤 {username}  |  Invested: €****  |  Value: €****  |  P&L: €****"
        else:
            label = (
                f"👤 {username}  |  Invested: €{invested_eur:,.2f}  |  "
                f"Value: €{val_eur:,.2f}  |  P&L: {pnl_sign}€{abs(pnl_eur):,.2f} ({pnl_sign}{ret_pct:.1f}%)  |  🎯 {breakdown_str}"
            )

        with st.expander(label, expanded=False):
            st.caption(
                f"**Positions:** {mirror_info.get('positions_count', len(underlying))}  |  "
                f"**Available Cash:** ${mirror_info.get('available_cash_usd', 0.0):,.2f}"
            )

            if underlying:
                u_items = []
                for p in underlying:
                    sym = p.get("symbol") or f"ID_{p.get('instrument_id')}"
                    p_val_usd = float(p.get("amount_usd", 0.0)) + float(p.get("pnl_usd", 0.0))
                    u_items.append({
                        "Symbol": sym,
                        "Name": p.get("name") or sym,
                        "Value ($)": f"${p_val_usd:,.2f}" if not ui.pages.investments.is_hidden() else "$****",
                        "Value (€)": f"€{p_val_usd * usd_to_eur:,.2f}" if not ui.pages.investments.is_hidden() else "€****",
                    })
                u_df = pd.DataFrame(u_items)
                st.dataframe(u_df, use_container_width=True, hide_index=True)


def render_holdings_table(holdings_df: pd.DataFrame) -> None:
    df_disp = holdings_df.copy()
    is_copy = df_disp["ticker"].str.startswith("COPY:", na=False)
    df_disp["Position Type"] = is_copy.map(
        lambda c: f"Copy: {c.replace('COPY:', '')}" if str(c).startswith("COPY:") else "Direct Holding"
    )
    df_disp["Position Type"] = [
        f"Copy: {t.replace('COPY:', '')}" if t.startswith("COPY:") else "Direct Holding"
        for t in df_disp["ticker"]
    ]

    df_disp["Avg Open Price"] = (
        df_disp["cost_basis_native"] / df_disp["quantity"]
    ).fillna(0)

    delayed_mask = (df_disp["latest_close"] <= 0) | df_disp["latest_close"].isna()
    df_disp["Quote Status"] = delayed_mask.map(
        lambda d: "⏱️ Quote delayed" if d else "🟢 Live"
    )
    df_disp["Market Price"] = df_disp["latest_close"]
    df_disp.loc[delayed_mask, "Market Price"] = df_disp.loc[delayed_mask, "Avg Open Price"]

    df_disp["P&L (€)"] = df_disp["unrealized_pnl_eur"]
    df_disp["P&L (%)"] = (
        df_disp["unrealized_pnl_eur"] / df_disp["cost_basis"] * 100
    ).fillna(0)

    disp_cols = {
        "ticker": "Ticker",
        "name": "Asset Name",
        "Position Type": "Type",
        "asset_type": "Asset Class",
        "quantity": "Units",
        "Avg Open Price": "Avg Open",
        "cost_basis": "Cost Basis (€)",
        "Market Price": "Current Price",
        "value_eur": "Value (€)",
        "P&L (€)": "P&L (€)",
        "P&L (%)": "P&L (%)",
        "Quote Status": "Status",
    }
    out_df = df_disp.rename(columns=disp_cols)[list(disp_cols.values())]

    if ui.pages.investments.is_hidden():
        out_df["Asset Name"] = "****"
        out_df["Ticker"] = "****"
        for col in [
            "Units",
            "Avg Open",
            "Cost Basis (€)",
            "Current Price",
            "Value (€)",
            "P&L (€)",
        ]:
            out_df[col] = "****"
        out_df["P&L (%)"] = "****%"
    else:
        out_df["Units"] = out_df["Units"].map(lambda x: f"{x:,.4f}")
        for col in ["Avg Open", "Current Price"]:
            out_df[col] = out_df[col].map(lambda x: f"{x:,.2f}")
        for col in ["Cost Basis (€)", "Value (€)"]:
            out_df[col] = out_df[col].map(lambda x: f"€{x:,.2f}")
        out_df["P&L (€)"] = out_df["P&L (€)"].map(
            lambda x: f"{'+' if x >= 0 else ''}€{x:,.2f}"
        )
        out_df["P&L (%)"] = out_df["P&L (%)"].map(lambda x: f"{x:+.1f}%")

    st.dataframe(out_df, use_container_width=True, hide_index=True)
