import streamlit as st

from agent.copilot import run_copilot


def render_copilot_sidebar() -> None:
    """Renders the persistent Copilot 365 sidebar assistant."""
    if "copilot_history" not in st.session_state:
        st.session_state.copilot_history = []

    st.markdown("### 🤖 Copilot 365")
    st.caption("Local AI assistant for queries, risk profiling, file parsing & app control.")

    # Quick action chips
    with st.expander("⚡ Quick Copilot Actions", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            if st.button("🎯 Assess Risk", use_container_width=True, key="btn_quick_risk"):
                st.session_state["pending_copilot_prompt"] = "Help me determine my investment risk tolerance and build a risk profile."
            if st.button("🏷️ Categorize", use_container_width=True, key="btn_quick_cat"):
                st.session_state["pending_copilot_prompt"] = "Categorize any uncategorized transactions using AI."
        with c2:
            if st.button("⚖️ Check Drift", use_container_width=True, key="btn_quick_drift"):
                st.session_state["pending_copilot_prompt"] = "Review my current portfolio balance against my target allocation and risk profile."
            if st.button("💡 App Guide", use_container_width=True, key="btn_quick_guide"):
                st.session_state["pending_copilot_prompt"] = "How do I configure bank connections and use this app?"

        if st.button("🗑️ Clear Copilot Chat", use_container_width=True, key="btn_clear_copilot"):
            st.session_state.copilot_history = []
            st.rerun()

    # File dropzone directly inside Copilot
    with st.expander("📎 Give Files to Copilot (Import)", expanded=False):
        st.caption("Upload bank or broker statements (PDF, CSV, TAB, XML, MT940). Copilot will parse and insert them.")
        uploaded_file = st.file_uploader(
            "Upload file",
            type=["csv", "tsv", "tab", "xml", "txt", "sta", "940", "pdf"],
            key="copilot_file_uploader",
            label_visibility="collapsed",
        )
        if uploaded_file is not None:
            if st.button("Process & Insert File", type="primary", use_container_width=True, key="btn_process_copilot_file"):
                with st.spinner(f"Copilot is analyzing '{uploaded_file.name}'..."):
                    bytes_data = uploaded_file.read()
                    file_info = [{"name": uploaded_file.name, "bytes": bytes_data}]
                    res = run_copilot(
                        user_message=f"I have uploaded file: {uploaded_file.name}",
                        history=st.session_state.copilot_history,
                        uploaded_files=file_info,
                    )
                    st.session_state.copilot_history.append({"role": "user", "content": f"Uploaded file: `{uploaded_file.name}`"})
                    st.session_state.copilot_history.append(res)
                    st.rerun()

    # Chat history display in sidebar container
    history_container = st.container(height=380)
    with history_container:
        if not st.session_state.copilot_history:
            st.info("👋 Hi! I can parse files, adjust settings, track your risk tolerance, or analyze spending. Try asking a question or pick a quick action above.")
        for msg in st.session_state.copilot_history:
            role = msg.get("role", "assistant")
            with st.chat_message(role):
                st.markdown(msg.get("content", ""))
                if msg.get("figure"):
                    st.plotly_chart(msg["figure"], use_container_width=True)
                if msg.get("df") is not None and not msg["df"].empty:
                    st.dataframe(msg["df"], use_container_width=True, hide_index=True)
                if msg.get("sql"):
                    with st.expander("Generated SQL"):
                        st.code(msg["sql"], language="sql")

    # Handle pending prompt from quick action buttons
    prompt_to_run = None
    if "pending_copilot_prompt" in st.session_state:
        prompt_to_run = st.session_state.pop("pending_copilot_prompt")

    # Chat input in sidebar
    user_input = st.sidebar.chat_input("Ask Copilot anything...", key="copilot_chat_input") or prompt_to_run

    if user_input:
        st.session_state.copilot_history.append({"role": "user", "content": user_input})
        with st.spinner("Copilot thinking..."):
            response = run_copilot(user_input, history=st.session_state.copilot_history)
            st.session_state.copilot_history.append(response)
        st.rerun()
