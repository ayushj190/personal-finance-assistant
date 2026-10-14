import streamlit as st
from agent.copilot_task import CopilotTask
from services.llm_client import check_ollama_status
from ui import state
from ui.components import mask_if_hidden
from ui.page_panel import clear_panel, set_panel
from ui.theme import render_chart

# One click navigation chips (AC-9): page, tab, preset. Different from the demo chips (AC-17).
NAV_CHIPS = [
    ("🗓️ Spending this month", "spending", None, "MTD"),
    ("📉 Spending last 3 months", "spending", None, "Last 3 Months"),
    ("📊 Investments holdings", "investments", "portfolio", None),
    ("⚖️ Allocation and Drift", "investments", "allocation", None),
    ("🧾 Transactions recent", "transactions", None, "Last 3 Months"),
    ("🏛️ Tax situation", "tax", None, None),
]

DEMO_PROMPTS = [
    "What is my net worth and how has it changed this year?",
    "Show my spending for the past 3 months.",
    "Review my portfolio allocation against my target.",
    "What can I do to lower my Dutch tax bill?",
]


def _set_intent(page: str, tab: str | None = None, preset: str | None = None) -> None:
    """Write a navigation intent directly from a chip or button (no model, no thread)."""
    st.session_state[state.K.COPILOT_UI_INTENT] = {
        "page": page,
        "tab": tab,
        "date_scope": {"requested": bool(preset), "preset": preset},
        "source": "chip",
    }


def render_copilot_sidebar() -> None:
    """Renders the snappy, tool-calling Copilot sidebar assistant with non-blocking fragment execution."""
    if "copilot_history" not in st.session_state:
        st.session_state.copilot_history = []

    is_busy = "copilot_active_task" in st.session_state

    # Sticky sidebar header: brand row, actions, and file import
    header_container = st.container(key="sticky_sidebar_header")
    with header_container:
        from core.config import DEMO

        if DEMO:
            st.markdown(
                "**:material/savings: Finance Assistant** &nbsp; "
                "<span style='background:#f59e0b;color:#111827;font-size:11px;font-weight:700;padding:2px 6px;border-radius:4px;'>DEMO</span>",
                unsafe_allow_html=True,
            )
            with st.expander("✨ Demo prompts", expanded=False):
                for i, demo_prompt in enumerate(DEMO_PROMPTS):
                    if st.button(demo_prompt, width="stretch", key=f"demo_prompt_{i}", disabled=is_busy):
                        st.session_state.copilot_history.append({"role": "user", "content": demo_prompt})
                        st.session_state["pending_copilot_prompt"] = demo_prompt
                        st.rerun(scope="app")
        else:
            st.markdown("**:material/savings: Finance Assistant**")

        col_acts, col_files = st.columns(2)
        with col_acts:
            with st.popover("⚡ Actions", width="stretch"):
                st.caption("Navigate")
                for label, page, tab, preset in NAV_CHIPS:
                    if st.button(label, width="stretch", disabled=is_busy, key=f"navchip_{page}_{tab}_{preset}"):
                        _set_intent(page, tab, preset)
                        st.rerun(scope="app")
                st.divider()
                st.caption("Ask")
                if st.button("🎯 Assess Risk", width="stretch", disabled=is_busy):
                    prompt = "Help me determine my investment risk tolerance and build a risk profile."
                    st.session_state.copilot_history.append({"role": "user", "content": prompt})
                    st.session_state["pending_copilot_prompt"] = prompt
                    st.rerun(scope="app")
                if st.button("🏷️ Categorize", width="stretch", disabled=is_busy):
                    prompt = "Categorize any uncategorized transactions using AI."
                    st.session_state.copilot_history.append({"role": "user", "content": prompt})
                    st.session_state["pending_copilot_prompt"] = prompt
                    st.rerun(scope="app")
                if st.button("⚖️ Check Drift", width="stretch", disabled=is_busy):
                    prompt = "Review my current portfolio balance against my target allocation and risk profile."
                    st.session_state.copilot_history.append({"role": "user", "content": prompt})
                    st.session_state["pending_copilot_prompt"] = prompt
                    st.rerun(scope="app")
                if st.button("💡 App Guide", width="stretch", disabled=is_busy):
                    prompt = "How do I configure bank connections and use this app?"
                    st.session_state.copilot_history.append({"role": "user", "content": prompt})
                    st.session_state["pending_copilot_prompt"] = prompt
                    st.rerun(scope="app")
                st.divider()
                if st.button("🗑️ Clear Chat", width="stretch"):
                    st.session_state.pop("copilot_active_task", None)
                    st.session_state.pop(state.K.COPILOT_UI_INTENT, None)
                    st.session_state.pop(state.K.COPILOT_WRITE_TOKEN, None)
                    clear_panel()
                    st.session_state.copilot_history = []
                    st.rerun(scope="app")

        uploaded_file_to_process = None
        with col_files:
            with st.popover("📎 Import", width="stretch"):
                st.caption("Upload bank or broker statements")
                uploaded_file = st.file_uploader(
                    "Upload file",
                    type=["csv", "tsv", "tab", "xml", "txt", "sta", "940", "pdf"],
                    key="copilot_file_uploader",
                    label_visibility="collapsed",
                )
                if uploaded_file is not None:
                    if st.button("Process File", type="primary", width="stretch", disabled=is_busy):
                        uploaded_file_to_process = uploaded_file

    # Dedicated scrollable chat history panel wrapped in a non-blocking fragment.
    # When a task is active, the fragment refreshes every 1s independently without rerunning the main page.
    # When idle, interval is None so no polling or DOM clearing occurs.
    interval = 1 if is_busy else None

    @st.fragment(run_every=interval)
    def _render_chat_history() -> None:
        history_container = st.container(key="copilot_chat_history", border=True)
        with history_container:
            if not st.session_state.copilot_history and "copilot_active_task" not in st.session_state:
                st.info("Local AI assistant with native tool-calling for net worth, spending, taxes, and investments.")

            for msg in st.session_state.copilot_history:
                role = msg.get("role", "assistant")
                avatar_map = {"user": "👤", "assistant": "🤖"}
                with st.chat_message(role, avatar=avatar_map.get(role)):
                    marker_cls = "chat-user-marker" if role == "user" else "chat-assistant-marker"
                    content = msg.get("content", "")
                    if role != "user":
                        content = mask_if_hidden(content)
                    st.markdown(
                        f'<span class="{marker_cls}" style="display:none;"></span>' + content,
                        unsafe_allow_html=True,
                    )
                    if msg.get("figure"):
                        render_chart(msg["figure"], width="stretch")
                    if msg.get("df") is not None and not msg["df"].empty:
                        st.dataframe(msg["df"], width="stretch", hide_index=True)
                    if msg.get("citations"):
                        with st.expander(f"📜 Verified Statutory Citations ({len(msg['citations'])})", expanded=False):
                            for cit in msg["citations"]:
                                art = cit.get("article_ref", "")
                                stat = cit.get("statute_title", "")
                                yr = cit.get("effective_year", 2026)
                                sc = cit.get("score")
                                score_badge = f" • Match: {int(sc*100)}%" if sc is not None else ""
                                st.markdown(f"**{art}** — *{stat}* ({yr}){score_badge}")
                                if cit.get("summary"):
                                    st.caption(cit["summary"])
                                if cit.get("juriconnect_ref"):
                                    st.caption(f"Ref: `{cit['juriconnect_ref']}`")
                                with st.expander("Verbatim statutory text"):
                                    st.markdown(cit.get("content", ""))
                                st.divider()
                    if msg.get("diagnostics"):
                        with st.expander(f"🛠️ Troubleshooting & Technical Diagnostics ({len(msg['diagnostics'])})", expanded=False):
                            for diag in msg["diagnostics"]:
                                tool_name = diag.get("tool", "Unknown Tool")
                                err_type = diag.get("error_type", "Notice")
                                err_details = diag.get("error_details", "")
                                st.markdown(f"**Tool:** `{tool_name}` • **Type:** `{err_type}`")
                                if err_details:
                                    st.code(err_details, language="text")
                                if diag.get("arguments"):
                                    st.caption(f"Arguments: `{diag['arguments']}`")
                                if diag.get("traceback"):
                                    with st.expander("Technical Traceback", expanded=False):
                                        st.code(diag["traceback"], language="python")
                                st.divider()
                    if msg.get("elapsed_seconds"):
                        # AC-17: turn time and model name in the answer footer.
                        model_label = f" · {msg['model']}" if msg.get("model") else ""
                        st.caption(f"⏱️ {msg['elapsed_seconds']:.1f}s{model_label}")

            active_task: CopilotTask | None = st.session_state.get("copilot_active_task")
            if active_task:
                with st.chat_message("assistant", avatar="🤖"):
                    st.markdown('<span class="chat-assistant-marker" style="display:none;"></span>', unsafe_allow_html=True)
                    if active_task.status == "thinking":
                        st.markdown(
                            """
                            <div class="copilot-thinking-card">
                                <div class="thinking-spinner">
                                    <span class="thinking-dot"></span>
                                    <span class="thinking-dot"></span>
                                    <span class="thinking-dot"></span>
                                </div>
                                <span class="thinking-label">Copilot is thinking...</span>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                    elif active_task.status == "error":
                        err_text = active_task.error or "An unexpected error occurred."
                        st.error(f"⚠️ {err_text}")
                        st.session_state.copilot_history.append({
                            "role": "assistant",
                            "content": f"⚠️ {err_text}",
                            "diagnostics": [{
                                "tool": "CopilotTask",
                                "error_type": "RuntimeError",
                                "error_details": err_text,
                            }],
                        })
                        st.session_state.pop("copilot_active_task", None)
                        st.rerun(scope="app")
                    elif active_task.status in ("typing", "completed"):
                        with active_task._lock:
                            chunks_snapshot = list(active_task.chunks)
                            curr_status = active_task.status
                            fig = active_task.figure
                            headline = getattr(active_task, "headline", None)
                            df = active_task.df
                            form_req = getattr(active_task, "form_request", None)
                            cits = getattr(active_task, "citations", None)
                            diags = getattr(active_task, "diagnostics", None)
                            elapsed = getattr(active_task, "elapsed_seconds", None)
                            model_name = getattr(active_task, "model_name", None)

                        text_so_far = "".join(chunks_snapshot)
                        if curr_status != "completed":
                            st.markdown(
                                """
                                <div class="copilot-typing-pill">
                                    <span class="typing-dot-small"></span>
                                    <span>Copilot is typing...</span>
                                </div>
                                """,
                                unsafe_allow_html=True,
                            )
                            if text_so_far:
                                st.markdown(mask_if_hidden(text_so_far))
                        else:
                            if text_so_far:
                                st.markdown(mask_if_hidden(text_so_far))
                            if fig:
                                render_chart(fig, width="stretch")
                            if df is not None and not df.empty:
                                st.dataframe(df, width="stretch", hide_index=True)
                            if cits:
                                with st.expander(f"📜 Verified Statutory Citations ({len(cits)})", expanded=False):
                                    for cit in cits:
                                        art = cit.get("article_ref", "")
                                        stat = cit.get("statute_title", "")
                                        yr = cit.get("effective_year", 2026)
                                        sc = cit.get("score")
                                        score_badge = f" • Match: {int(sc*100)}%" if sc is not None else ""
                                        st.markdown(f"**{art}** — *{stat}* ({yr}){score_badge}")
                                        if cit.get("summary"):
                                            st.caption(cit["summary"])
                                        if cit.get("juriconnect_ref"):
                                            st.caption(f"Ref: `{cit['juriconnect_ref']}`")
                                        with st.expander("Verbatim statutory text"):
                                            st.markdown(cit.get("content", ""))
                                        st.divider()
                            if diags:
                                with st.expander(f"🛠️ Troubleshooting & Technical Diagnostics ({len(diags)})", expanded=False):
                                    for diag in diags:
                                        tool_name = diag.get("tool", "Unknown Tool")
                                        err_type = diag.get("error_type", "Notice")
                                        err_details = diag.get("error_details", "")
                                        st.markdown(f"**Tool:** `{tool_name}` • **Type:** `{err_type}`")
                                        if err_details:
                                            st.code(err_details, language="text")
                                        if diag.get("arguments"):
                                            st.caption(f"Arguments: `{diag['arguments']}`")
                                        if diag.get("traceback"):
                                            with st.expander("Technical Traceback", expanded=False):
                                                st.code(diag["traceback"], language="python")
                                        st.divider()

                            st.session_state.copilot_history.append({
                                "role": "assistant",
                                "content": text_so_far,
                                "figure": fig,
                                "df": df,
                                "citations": cits,
                                "diagnostics": diags,
                                "elapsed_seconds": elapsed,
                                "model": model_name,
                            })
                            if getattr(active_task, "ui_intent", None):
                                intent = active_task.ui_intent
                                st.session_state[state.K.COPILOT_UI_INTENT] = intent
                                # One panel per page, keyed by page id, replaces the last one (AC-3).
                                panel_page = intent.get("page")
                                if fig is not None and panel_page:
                                    set_panel(panel_page, fig, headline)
                            st.session_state.pop("copilot_active_task", None)

                            if form_req:
                                st.session_state["pending_form"] = form_req
                            st.rerun(scope="app")

    _render_chat_history()

    # Prompt check
    pending_prompt = st.session_state.pop("pending_copilot_prompt", None)
    chat_placeholder = "Copilot is thinking..." if is_busy else "Ask Copilot anything..."
    chat_input_val = st.chat_input(chat_placeholder, key="copilot_chat_input", disabled=is_busy)
    user_prompt = chat_input_val or pending_prompt

    if uploaded_file_to_process and not is_busy:
        clear_panel()  # a new turn replaces the panel (AC-3)
        user_msg = f"Uploaded statement: `{uploaded_file_to_process.name}`"
        st.session_state.copilot_history.append({"role": "user", "content": user_msg})

        ollama_status = check_ollama_status()
        if not ollama_status.get("online", False):
            err_msg = (
                "⚠️ Local Ollama is offline or unreachable.\n\n"
                "Please start Ollama on your machine:\n"
                "```bash\n"
                "ollama serve\n"
                "```\n"
                "Once Ollama is running, retry processing your statement."
            )
            st.session_state.copilot_history.append({
                "role": "assistant",
                "content": err_msg,
                "diagnostics": [{
                    "tool": "OllamaHealthCheck",
                    "error_type": "ConnectionRefused",
                    "error_details": ollama_status.get("error") or "Ollama daemon unreachable.",
                }],
            })
            st.rerun(scope="app")

        bytes_data = uploaded_file_to_process.read()
        file_info = [{"name": uploaded_file_to_process.name, "bytes": bytes_data}]
        task = CopilotTask(
            prompt=user_msg,
            history=st.session_state.copilot_history[:-1],
            uploaded_files=file_info,
        )
        task.start()
        st.session_state["copilot_active_task"] = task
        st.rerun(scope="app")

    elif user_prompt and not is_busy:
        clear_panel()  # a new turn replaces the panel (AC-3)
        if chat_input_val:
            st.session_state.copilot_history.append({"role": "user", "content": chat_input_val})
        elif pending_prompt:
            if not st.session_state.copilot_history or st.session_state.copilot_history[-1].get("content") != pending_prompt:
                st.session_state.copilot_history.append({"role": "user", "content": pending_prompt})

        ollama_status = check_ollama_status()
        if not ollama_status.get("online", False):
            err_msg = (
                "⚠️ Local Ollama is offline or unreachable.\n\n"
                "Please start Ollama on your machine:\n"
                "```bash\n"
                "ollama serve\n"
                "```\n"
                "Once Ollama is running, submit your question again."
            )
            st.session_state.copilot_history.append({
                "role": "assistant",
                "content": err_msg,
                "diagnostics": [{
                    "tool": "OllamaHealthCheck",
                    "error_type": "ConnectionRefused",
                    "error_details": ollama_status.get("error") or "Ollama daemon unreachable.",
                }],
            })
            st.rerun(scope="app")

        task = CopilotTask(
            prompt=user_prompt,
            history=st.session_state.copilot_history[:-1],
        )
        task.start()
        st.session_state["copilot_active_task"] = task
        st.rerun(scope="app")

    # Render any pending modal dialogs
    if st.session_state.get("pending_form") == "tax_profile":
        from ui.dialogs import tax_profile_dialog
        tax_profile_dialog()
    elif st.session_state.get("pending_form") == "risk_profile":
        from ui.dialogs import risk_profile_dialog
        risk_profile_dialog()
    elif st.session_state.get("pending_form") == "mortgage_config":
        from ui.dialogs import mortgage_config_dialog
        mortgage_config_dialog()
