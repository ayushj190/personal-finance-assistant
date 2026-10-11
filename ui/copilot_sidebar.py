import streamlit as st
from agent.copilot_task import CopilotTask


def render_copilot_sidebar() -> None:
    """Renders the snappy, tool-calling Copilot sidebar assistant with non-blocking fragment execution."""
    if "copilot_history" not in st.session_state:
        st.session_state.copilot_history = []

    is_busy = "copilot_active_task" in st.session_state

    # Sticky sidebar header: title, actions, and file import
    header_container = st.container(key="sticky_sidebar_header")
    with header_container:
        st.markdown(
            "<h1 style='margin-top: 0.0rem; margin-bottom: 0.5rem;'>Personal Finance Assistant</h1>",
            unsafe_allow_html=True,
        )

        col_acts, col_files = st.columns(2)
        with col_acts:
            with st.popover("⚡ Actions", use_container_width=True):
                if st.button("🎯 Assess Risk", use_container_width=True, disabled=is_busy):
                    st.session_state["pending_copilot_prompt"] = "Help me determine my investment risk tolerance and build a risk profile."
                    st.rerun(scope="app")
                if st.button("🏷️ Categorize", use_container_width=True, disabled=is_busy):
                    st.session_state["pending_copilot_prompt"] = "Categorize any uncategorized transactions using AI."
                    st.rerun(scope="app")
                if st.button("⚖️ Check Drift", use_container_width=True, disabled=is_busy):
                    st.session_state["pending_copilot_prompt"] = "Review my current portfolio balance against my target allocation and risk profile."
                    st.rerun(scope="app")
                if st.button("💡 App Guide", use_container_width=True, disabled=is_busy):
                    st.session_state["pending_copilot_prompt"] = "How do I configure bank connections and use this app?"
                    st.rerun(scope="app")
                st.divider()
                if st.button("🗑️ Clear Chat", use_container_width=True):
                    st.session_state.pop("copilot_active_task", None)
                    st.session_state.copilot_history = []
                    st.rerun(scope="app")

        uploaded_file_to_process = None
        with col_files:
            with st.popover("📎 Import", use_container_width=True):
                st.caption("Upload bank or broker statements")
                uploaded_file = st.file_uploader(
                    "Upload file",
                    type=["csv", "tsv", "tab", "xml", "txt", "sta", "940", "pdf"],
                    key="copilot_file_uploader",
                    label_visibility="collapsed",
                )
                if uploaded_file is not None:
                    if st.button("Process File", type="primary", use_container_width=True, disabled=is_busy):
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
                    st.markdown(
                        f'<span class="{marker_cls}" style="display:none;"></span>' + msg.get("content", ""),
                        unsafe_allow_html=True,
                    )
                    if msg.get("figure"):
                        st.plotly_chart(msg["figure"], use_container_width=True, theme=None)
                    if msg.get("df") is not None and not msg["df"].empty:
                        st.dataframe(msg["df"], use_container_width=True, hide_index=True)
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
                        })
                        st.session_state.pop("copilot_active_task", None)
                        st.rerun(scope="app")
                    elif active_task.status in ("typing", "completed"):
                        with active_task._lock:
                            chunks_snapshot = list(active_task.chunks)
                            curr_status = active_task.status
                            fig = active_task.figure
                            df = active_task.df
                            form_req = getattr(active_task, "form_request", None)
                            cits = getattr(active_task, "citations", None)

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
                                st.markdown(text_so_far)
                        else:
                            if text_so_far:
                                st.markdown(text_so_far)
                            if fig:
                                st.plotly_chart(fig, use_container_width=True, theme=None)
                            if df is not None and not df.empty:
                                st.dataframe(df, use_container_width=True, hide_index=True)
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

                            st.session_state.copilot_history.append({
                                "role": "assistant",
                                "content": text_so_far,
                                "figure": fig,
                                "df": df,
                                "citations": cits,
                            })
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
        user_msg = f"Uploaded statement: `{uploaded_file_to_process.name}`"
        st.session_state.copilot_history.append({"role": "user", "content": user_msg})
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
        st.session_state.copilot_history.append({"role": "user", "content": user_prompt})
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
