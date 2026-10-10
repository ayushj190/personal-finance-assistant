from datetime import date, datetime
import sqlite3
from textwrap import dedent
import httpx
import pandas as pd
import streamlit as st

from config import DATA_DIR, DB_PATH, DEFAULT_MODEL, DEFAULT_OLLAMA_URL
from db import database
from services import secrets_vault
from services.mortgage import sync_liability_schedule
from ui.components import section_header


def render():

    conn = database.connect(DB_PATH)

    tab_conn, tab_mortgage, tab_alloc, tab_llm, tab_appearance, tab_system = st.tabs(
        ["Bank & Broker Integrations", "Mortgage & Liabilities",
            "Target Allocations", "AI Model (Ollama)", "Appearance", "Database & Backup"]
    )

    # 1. Integrations Tab
    with tab_conn:
        section_header("Direct Bank Linking (Open Banking / PSD2)",
                       "Connect ABN AMRO, Revolut, ING, or Rabobank directly")

        from connectors.enable_banking_service import EnableBankingService, generate_rsa_keypair

        eb_service = EnableBankingService()
        is_eb_configured = eb_service.is_configured()

        # Top Sync Actions
        col_sync_act, col_sync_info = st.columns([1, 2])
        with col_sync_act:
            last_sync_row = conn.execute(
                "SELECT started_at FROM sync_log ORDER BY started_at DESC LIMIT 1").fetchone()
            last_sync_text = ""
            if last_sync_row and last_sync_row["started_at"]:
                last_time_str = last_sync_row["started_at"].replace("T", " ")[:16]
                last_sync_text = f"Last synced: {last_time_str}"
            
            if st.button("🔄 Sync All Banks & Brokers", type="primary", use_container_width=True, help="Trigger manual sync across all active connectors and market data"):
                with st.spinner("Syncing bank & broker data..."):
                    from services.sync_service import sync_all
                    sync_all(conn)
                    st.success("Sync completed successfully!")
                    st.rerun()
            if last_sync_text:
                st.caption(last_sync_text)
        with col_sync_info:
            if is_eb_configured:
                st.success("✅ Open Banking service is configured and active.")
            else:
                st.info(
                    "ℹ️ Open Banking uses free European PSD2 keys. See setup guide below.")

        # Bank Selection Grid with dynamic dropdown
        st.markdown("### Supported Banks (PSD2 Direct Sync)")

        @st.cache_data(ttl=3600)
        def get_bank_options() -> list:
            if is_eb_configured:
                try:
                    return eb_service.get_aspsps()
                except Exception:
                    pass
            return []

        if not is_eb_configured:
            st.warning(
                "⚠️ Enable Banking API credentials must be saved first (see the setup guide below) to fetch the list of banks.")
        else:
            aspsps = get_bank_options()
            if aspsps:
                featured_opts = {}
                other_opts = {}
                
                for b in aspsps:
                    name = b.get("name", "Unknown")
                    country = b.get("country", "Unknown")
                    label = f"{name} ({country})"
                    
                    if country == "NL" or "trade republic" in name.lower() or "revolut" in name.lower():
                        featured_opts[label] = b
                    else:
                        other_opts[label] = b

                show_all = st.toggle("Show all European banks (Advanced)")
                active_opts = {**featured_opts, **other_opts} if show_all else featured_opts

                selected_bank_key = st.selectbox(
                    "Select your Bank to Connect", options=sorted(active_opts.keys()))

                c_connect, c_status = st.columns([1, 2])
                with c_connect:
                    if st.button("Connect Selected Bank", type="primary", use_container_width=True):
                        bank_data = active_opts[selected_bank_key]
                        bank_name = bank_data.get("name", "Unknown")
                        bank_country = bank_data.get("country", "NL")
                        bank_slug = bank_name.lower().replace(" ", "_").replace("-", "_")
                        st.session_state["connect_bank"] = (
                            bank_name, bank_country, bank_slug)
                with c_status:
                    if selected_bank_key:
                        bank_data = active_opts[selected_bank_key]
                        bank_name = bank_data.get("name", "Unknown")
                        bank_slug_preview = bank_name.lower().replace(" ", "_").replace("-", "_")
                        session_key = f"eb_session_{bank_slug_preview}"
                        if secrets_vault.get(session_key) or (bank_slug_preview == "abn_amro" and secrets_vault.get("eb_session_id")):
                            valid_until = secrets_vault.get(
                                f"{session_key}_valid_until")
                            valid_badge = f"🟢 Currently Connected (`{valid_until[:10]}`)" if valid_until else "🟢 Currently Connected"
                            st.markdown(valid_badge)

        # Bank Authorization Flow
        if "connect_bank" in st.session_state:
            bank_name, country, bank_slug = st.session_state["connect_bank"]
            session_key = f"eb_session_{bank_slug}"
            eb_bank_service = EnableBankingService(
                session_vault_key=session_key)

            st.markdown(f"### Connecting to **{bank_name}**")

            if st.button(f"🔗 Authorize with {bank_name} (Official Bank Portal)", type="primary"):
                try:
                    auth_url = eb_bank_service.start_auth(
                        aspsp_name=bank_name, country=country)
                    st.session_state["auth_url"] = auth_url
                except Exception as e:
                    st.error(
                        f"Failed to initiate bank authorization: {str(e)}")

            if "auth_url" in st.session_state:
                st.markdown(
                    f"[👉 **Click here to open {bank_name} login**]({st.session_state['auth_url']})")
                st.caption(
                    "Log in or authorize in the test portal. The bank will redirect to your `https://localhost:8501/` callback URL.")
                st.info("💡 **Localhost redirect tip**: If your browser shows a blank page, SSL warning, or 'Unable to connect' after redirecting to `https://localhost:8501/`, that's completely normal! Just copy the entire URL from your browser's address bar (or the `code=...` part) and paste it below.")

                auth_code_input = st.text_input(
                    "Paste Redirect URL or Code parameter here:")
                c_done, c_cancel = st.columns([1, 1])
                with c_done:
                    if st.button("Complete Account Connection", type="primary"):
                        code = auth_code_input.strip()
                        if "code=" in code:
                            import urllib.parse
                            parsed = urllib.parse.urlparse(code)
                            query_params = urllib.parse.parse_qs(parsed.query)
                            code = query_params.get("code", [code])[0]

                        try:
                            eb_bank_service.complete_auth(code)
                            accounts = eb_bank_service.fetch_accounts()
                            for acc in accounts:
                                database.upsert_account(
                                    conn,
                                    {
                                        "provider": "enable_banking",
                                        "institution": acc.institution,
                                        "external_id": acc.external_id,
                                        "name": acc.name,
                                        "currency": acc.currency,
                                        "asset_class": acc.asset_class,
                                        "iban": acc.iban,
                                    },
                                )
                            st.success(
                                f"Successfully connected {len(accounts)} account(s) from {bank_name}!")
                            del st.session_state["connect_bank"]
                            if "auth_url" in st.session_state:
                                del st.session_state["auth_url"]
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error completing connection: {str(e)}")
                with c_cancel:
                    if st.button("Cancel Connection"):
                        del st.session_state["connect_bank"]
                        if "auth_url" in st.session_state:
                            del st.session_state["auth_url"]
                        st.rerun()

        # Recent Sync Logs
        recent_syncs = conn.execute(
            "SELECT connector, started_at, status, message FROM sync_log ORDER BY started_at DESC LIMIT 5").fetchall()
        if recent_syncs:
            with st.expander("📋 View Recent Integration Sync Logs"):
                log_df = pd.DataFrame([dict(r) for r in recent_syncs])
                log_df.columns = ["Connector", "Time", "Status", "Details"]
                st.dataframe(log_df, use_container_width=True, hide_index=True)

        st.divider()

        # Guided Setup / Credentials Section
        with st.expander("🔑 Open Banking Credentials Setup Guide (Free & 2 Minutes)", expanded=not is_eb_configured):
            st.markdown(
                dedent(
                    """
                    **Why are these keys needed?**
                    European banking law (PSD2) requires all apps to cryptographically sign requests to communicate directly with banks.
                    Because this app is **100% private and runs locally on your PC** with no cloud company collecting your data,
                    you use your own free personal developer keys from **Enable Banking** (the official European banking gateway).
                    It is **completely free for personal use**.

                    ---
                    #### **Step-by-Step Instructions:**
                    1. Go to [enablebanking.com](https://enablebanking.com) and create a free account.
                    2. In the dashboard, click **Applications** → **Create Application**.
                    3. Enter name (e.g. `PFA Assistant`), and set Redirect URL to `https://localhost:8501/`.
                    4. Copy the **Application ID** and paste it below.
                    5. Provide the RSA Key: Click **"Generate RSA Key Pair For Me"** below, copy the public key into Enable Banking, and we'll automatically save the private key locally!
                    """
                ).strip()
            )

            c_gen, c_status = st.columns([1, 2])
            with c_gen:
                if st.button("✨ Generate RSA Key Pair For Me"):
                    priv_pem, pub_pem = generate_rsa_keypair()
                    secrets_vault.put("eb_key_pem", priv_pem)
                    st.session_state["generated_public_key"] = pub_pem
                    st.success(
                        "Private key generated and saved in local encrypted vault!")

            if "generated_public_key" in st.session_state:
                st.markdown(
                    "**Copy this Public Key into the Enable Banking Application form:**")
                st.code(
                    st.session_state["generated_public_key"], language="text")

            st.markdown("---")
            st.markdown("**Enter Your Credentials:**")
            eb_app_id = st.text_input("Enable Banking Application ID", value=secrets_vault.get(
                "eb_app_id") or "", placeholder="e.g. a1b2c3d4-...")

            uploaded_pem = st.file_uploader(
                "Or upload downloaded private key file (.pem)", type=["pem", "key", "txt"])
            if uploaded_pem:
                pem_text = uploaded_pem.read().decode("utf-8")
                secrets_vault.put("eb_key_pem", pem_text)
                st.success("Uploaded private key saved to vault!")

            eb_key_pem = st.text_area("Private Key (RSA PEM)", value=secrets_vault.get(
                "eb_key_pem") or "", height=80, placeholder="-----BEGIN PRIVATE KEY----- ...")

            if st.button("Save Enable Banking Credentials", type="primary"):
                if eb_app_id.strip():
                    secrets_vault.put("eb_app_id", eb_app_id.strip())
                if eb_key_pem.strip():
                    secrets_vault.put("eb_key_pem", eb_key_pem.strip())
                st.success(
                    "Credentials saved securely in local Windows vault!")
                st.rerun()

            st.info("💡 **Don't want to create developer keys?** You don't have to! You can simply export your monthly statement (CSV, TAB, or CAMT.053) from your banking app and drag it into the **Import** tab anytime.")

        st.divider()

        # eToro Section
        section_header("eToro Bank & Investment Integration",
                       "Direct API sync for cash balance, transactions, and portfolio holdings")
        st.info(
            "💡 **eToro Money & Trading API Sync:**\n\n"
            "Your eToro EUR cash balance, cash transactions, and USD trading portfolio are synced automatically via the official eToro API when configured."
        )

        with st.expander("eToro Trading Portfolio API Setup (Optional)"):
            st.markdown(
                dedent(
                    """
                    To automatically sync your open investment positions and stocks:
                    1. Log in to [api-portal.etoro.com](https://api-portal.etoro.com) with your eToro credentials.
                    2. Generate an **API Key** and **User Key**.
                    3. Paste both keys below:
                    """
                ).strip()
            )
            etoro_api_key = st.text_input("eToro API Key", value=secrets_vault.get(
                "etoro_api_key") or "", type="password")
            etoro_user_key = st.text_input("eToro User Key", value=secrets_vault.get(
                "etoro_user_key") or "", type="password")
            if st.button("Save eToro Keys"):
                secrets_vault.put("etoro_api_key", etoro_api_key.strip())
                secrets_vault.put("etoro_user_key", etoro_user_key.strip())
                st.success("eToro credentials saved!")

        st.divider()

        st.divider()

        # Savings Accounts & APY Configuration
        section_header("Savings Accounts & Balances",
                       "Adjust savings account balances (Trade Republic, bank savings) and set APY interest rates")
        cash_accounts = conn.execute(
            "SELECT id, institution, name, currency, apy FROM accounts WHERE asset_class = 'cash' AND is_active = 1 ORDER BY institution, name"
        ).fetchall()

        if cash_accounts:
            with st.form("savings_apy_form"):
                st.caption(
                    "Update current money/savings value or set the Annual Percentage Yield (APY) for your high-yield cash accounts (e.g., Trade Republic).")
                apy_inputs = {}
                balance_inputs = {}
                for acc in cash_accounts:
                    snap_row = conn.execute(
                        "SELECT balance_eur_minor FROM account_snapshots WHERE account_id = ? ORDER BY snapshot_date DESC LIMIT 1",
                        (acc["id"],),
                    ).fetchone()
                    if snap_row:
                        cur_bal = snap_row["balance_eur_minor"] / 100.0
                    else:
                        tx_sum = conn.execute(
                            "SELECT SUM(amount_eur_minor) AS total FROM transactions WHERE account_id = ?",
                            (acc["id"],),
                        ).fetchone()
                        cur_bal = (tx_sum["total"] or 0) / 100.0

                    col1, col2, col3 = st.columns([2, 1, 1])
                    with col1:
                        st.markdown(
                            f"**{acc['institution']}**\n\n{acc['name']} ({acc['currency']})")
                    with col2:
                        balance_inputs[acc["id"]] = st.number_input(
                            "Balance (€)",
                            value=float(cur_bal),
                            min_value=0.0,
                            step=50.0,
                            format="%.2f",
                            key=f"bal_{acc['id']}",
                        )
                    with col3:
                        current_apy = float(acc["apy"] or 0.0)
                        apy_inputs[acc["id"]] = st.number_input(
                            "APY %",
                            value=current_apy,
                            min_value=0.0,
                            max_value=25.0,
                            step=0.1,
                            format="%.2f",
                            key=f"apy_{acc['id']}",
                        )
                if st.form_submit_button("Save Balances & APY Rates", type="primary"):
                    today_str = date.today().isoformat()
                    with conn:
                        for acc_id, val in apy_inputs.items():
                            rate = val if val > 0 else None
                            conn.execute(
                                "UPDATE accounts SET apy = ? WHERE id = ?", (rate, acc_id))
                        snapshots_to_upsert = []
                        for acc_id, bal in balance_inputs.items():
                            b_minor = int(round(bal * 100))
                            snapshots_to_upsert.append({
                                "account_id": acc_id,
                                "snapshot_date": today_str,
                                "balance_minor": b_minor,
                                "balance_eur_minor": b_minor,
                            })
                        database.upsert_snapshots(conn, snapshots_to_upsert)
                    st.success("Savings balances and APY rates updated!")
                    st.rerun()

    # 2. Mortgage Tab
    with tab_mortgage:
        section_header("Mortgage Details (Leningdelen)",
                       "Annuity, Linear, or Interest-Only amortisation")
        existing_lib = conn.execute(
            "SELECT * FROM liabilities LIMIT 1").fetchone()
        existing_rp = None
        if existing_lib:
            existing_rp = conn.execute(
                "SELECT * FROM liability_rate_periods WHERE liability_id = ? ORDER BY from_date ASC LIMIT 1", (existing_lib["id"],)).fetchone()

        from ui.dialogs import mortgage_config_dialog
        if st.button("⚙️ Configure Mortgage / Loan", type="primary"):
            mortgage_config_dialog(existing_lib["id"] if existing_lib else None)

    # 3. Target Allocations Tab
    with tab_alloc:
        section_header("Asset Allocation Profiles",
                       "Configure portfolio target weights and tolerance bands")
        profiles = conn.execute(
            "SELECT * FROM allocation_profiles ORDER BY id ASC").fetchall()
        for p in profiles:
            with st.expander(f"Profile: {p['name']} ({'Active' if p['is_active'] else 'Inactive'})"):
                st.write(
                    f"Dimension: `{p['dimension']}` | Drift Tolerance: `±{p['drift_band_pct']} pp`")
                targets = conn.execute(
                    "SELECT bucket, target_pct FROM allocation_targets WHERE profile_id = ?", (p["id"],)).fetchall()
                for t in targets:
                    st.write(f"- **{t['bucket']}**: {t['target_pct']}%")
                if not p["is_active"]:
                    if st.button(f"Set '{p['name']}' as Active Profile", key=f"act_{p['id']}"):
                        with conn:
                            conn.execute(
                                "UPDATE allocation_profiles SET is_active = 0")
                            conn.execute(
                                "UPDATE allocation_profiles SET is_active = 1 WHERE id = ?", (p["id"],))
                        st.success(
                            f"'{p['name']}' is now the active allocation profile.")
                        st.rerun()

    # 4. LLM Tab
    with tab_llm:
        section_header("Local AI Copilot (Ollama)",
                       "Zero cloud telemetry, runs completely local")
        ollama_url = st.text_input("Ollama Endpoint URL", value=secrets_vault.get(
            "ollama_endpoint") or DEFAULT_OLLAMA_URL)
        ollama_model = st.text_input(
            "Ollama Model Name", value=secrets_vault.get("ollama_model") or DEFAULT_MODEL)
        brave_api_key = st.text_input("Brave Search API Key (Optional)", value=secrets_vault.get(
            "brave_api_key") or "", type="password", help="Enables live web search lookup for unknown merchants to improve categorization.")

        c_save, c_test = st.columns(2)
        with c_save:
            if st.button("Save AI & Search Settings"):
                secrets_vault.put("ollama_endpoint", ollama_url.strip())
                secrets_vault.put("ollama_model", ollama_model.strip())
                if brave_api_key:
                    secrets_vault.put("brave_api_key", brave_api_key.strip())
                st.success("AI & search settings saved!")

        with c_test:
            if st.button("Test Ollama Connection"):
                try:
                    with httpx.Client(timeout=5.0) as client:
                        resp = client.get(f"{ollama_url.rstrip('/')}/api/tags")
                        if resp.status_code == 200:
                            models = [m.get("name")
                                      for m in resp.json().get("models", [])]
                            st.success(
                                f"Connected to Ollama! Available models: {', '.join(models)}")
                        else:
                            st.error(
                                f"Ollama returned HTTP status {resp.status_code}")
                except Exception as e:
                    st.error(f"Connection failed: {str(e)}")

    # 5. Appearance & Theme Tab
    with tab_appearance:
        section_header("Appearance & Display", "Configure theme and visual preferences")
        current_theme = st.session_state.get("theme", "dark")
        is_dark = current_theme == "dark"

        c_toggle, c_info = st.columns([1, 2])
        with c_toggle:
            dark_mode = st.toggle(
                "🌙 Dark Mode",
                value=is_dark,
                key="settings_dark_mode_toggle",
                help="Switch between Dark and Light mode",
            )
            if dark_mode != is_dark:
                st.session_state["theme"] = "dark" if dark_mode else "light"
                st.rerun()
        with c_info:
            st.caption(f"Currently active: **{'Dark' if is_dark else 'Light'} Mode**")

    # 6. Database & Backup Tab
    with tab_system:
        section_header("Database Management", "Local SQLite backups")
        st.write(f"Database Path: `{DB_PATH}`")
        if st.button("Create Instant Database Backup"):
            backup_filename = f"finance_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
            backup_path = DATA_DIR / backup_filename
            b_conn = sqlite3.connect(str(backup_path))
            with b_conn:
                conn.backup(b_conn)
            b_conn.close()
            st.success(f"Database successfully backed up to `{backup_path}`!")

    conn.close()
