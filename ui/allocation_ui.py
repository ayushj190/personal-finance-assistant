"""Reusable create and delete controls for investment allocation strategies.

Used by Settings (Target Allocations) and the Investments allocation panel so
both surfaces share one write path and one confirmation flow (AC-11).
"""

import streamlit as st

from db.repositories import HoldingRepository
from services.allocation_service import (
    ALLOWED_DIMENSIONS,
    create_allocation_profile,
    delete_allocation_profile,
    get_valid_buckets,
)


def render_allocation_management(conn) -> None:
    """Render the create form and the confirmed delete controls for every saved profile."""
    _render_create_form(conn)
    _render_delete_controls(conn)


def _render_create_form(conn) -> None:
    with st.expander("➕ New Allocation Strategy", expanded=False):
        dimension = st.selectbox(
            "Dimension",
            options=list(ALLOWED_DIMENSIONS),
            format_func=lambda d: d.replace("_", " ").title(),
            key="alloc_new_dimension",
        )
        buckets = get_valid_buckets(conn, dimension)

        with st.form("alloc_create_form", clear_on_submit=False):
            name = st.text_input("Strategy Name")
            st.caption(
                "Give every bucket a target percent. The targets must sum to 100 "
                "(within 0.1) and the new strategy is not activated automatically."
            )
            targets: dict[str, float] = {}
            cols = st.columns(3)
            for i, bucket in enumerate(buckets):
                with cols[i % 3]:
                    targets[bucket] = st.number_input(
                        bucket,
                        min_value=0.0,
                        max_value=100.0,
                        step=0.1,
                        value=0.0,
                        format="%.1f",
                        key=f"alloc_target_{dimension}_{bucket}",
                    )
            col_band, col_cash = st.columns(2)
            with col_band:
                drift_band = st.number_input(
                    "Drift band (percentage points)",
                    min_value=0.0,
                    max_value=100.0,
                    step=1.0,
                    value=5.0,
                    key="alloc_new_drift_band",
                )
            with col_cash:
                include_cash = st.checkbox(
                    "Include cash bucket", value=False, key="alloc_new_include_cash"
                )
            submitted = st.form_submit_button("Create Strategy", type="primary")

        if submitted:
            result = create_allocation_profile(
                conn,
                name=name,
                dimension=dimension,
                targets=targets,
                drift_band_pct=drift_band,
                include_cash=include_cash,
            )
            if result.get("success"):
                st.success(result["message"])
                st.rerun()
            else:
                st.error(result["message"])


def _render_delete_controls(conn) -> None:
    profiles = HoldingRepository.get_allocation_profiles(conn)
    if not profiles:
        return

    st.markdown("##### Delete a strategy")
    for p in profiles:
        name = p["name"]
        token_key = f"alloc_delete_token_{name}"
        cols = st.columns([3, 1])
        with cols[0]:
            active = " — active" if p.get("is_active") else ""
            st.write(f"**{name}** ({p['dimension']}){active}")
        with cols[1]:
            if st.button("🗑️ Delete", key=f"alloc_delete_{name}"):
                result = delete_allocation_profile(conn, name)
                if result.get("requires_confirmation"):
                    st.session_state[token_key] = result["confirm_token"]
                    st.warning(result["message"])
                elif not result.get("success"):
                    st.error(result["message"])
                else:
                    st.success(result["message"])
                    st.rerun()

        token = st.session_state.get(token_key)
        if token:
            if st.button(f"Confirm delete '{name}'", key=f"alloc_delete_confirm_{name}"):
                result = delete_allocation_profile(conn, name, token)
                st.session_state.pop(token_key, None)
                if result.get("success"):
                    st.success(result["message"])
                    st.rerun()
                else:
                    st.error(result["message"])
