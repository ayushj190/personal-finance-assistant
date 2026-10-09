import streamlit as st
import threading
from streamlit.runtime.scriptrunner import add_script_run_ctx

from agent.copilot import run_copilot


def _copilot_worker(user_input: str, history_copy: list, state_dict: dict, uploaded_files: list = None):
    try:
        response = run_copilot(
            user_input, history=history_copy, uploaded_files=uploaded_files)
        state_dict["copilot_thread_result"] = response
    except Exception as e:
        state_dict["copilot_thread_result"] = {
            "role": "assistant", "content": f"Error: {e}"}


def render_copilot_sidebar() -> None:
    """Renders the persistent Copilot 365 sidebar assistant."""
    if "copilot_history" not in st.session_state:
        st.session_state.copilot_history = []
    if "copilot_is_thinking" not in st.session_state:
        st.session_state.copilot_is_thinking = False
    if "copilot_thread_result" not in st.session_state:
        st.session_state.copilot_thread_result = None

    @st.fragment(run_every=2 if st.session_state.get("copilot_is_thinking") else None)
    def render_chat_history():
        # If the thread just finished, process the result
        if st.session_state.get("copilot_thread_result") is not None:
            st.session_state.copilot_history.append(
                st.session_state.copilot_thread_result)
            st.session_state.copilot_thread_result = None
            st.session_state.copilot_is_thinking = False
            st.rerun()

        # Chat history display in sidebar container
        history_container = st.container(height=500, border=False)
        with history_container:
            if not st.session_state.copilot_history:
                st.info(
                    "Local AI assistant for queries, risk profiling, file parsing & app control.")
            for msg in st.session_state.copilot_history:
                role = msg.get("role", "assistant")
                avatar_map = {"user": "👤", "assistant": "🤖"}
                with st.chat_message(role, avatar=avatar_map.get(role)):
                    st.markdown(msg.get("content", ""))
                    if msg.get("figure"):
                        st.plotly_chart(
                            msg["figure"], use_container_width=True, theme=None)
                    if msg.get("df") is not None and not msg["df"].empty:
                        st.dataframe(
                            msg["df"], use_container_width=True, hide_index=True)
                    if msg.get("sql"):
                        with st.expander("Generated SQL"):
                            st.code(msg["sql"], language="sql")

            if st.session_state.get("copilot_is_thinking"):
                with st.chat_message("assistant", avatar="🤖"):
                    st.markdown("Thinking... ⏳")

    st.markdown("### 🤖 Assistant")

    # Quick actions and File dropzone side by side
    col_acts, col_files = st.columns(2)
    with col_acts:
        with st.popover("⚡ Actions", use_container_width=True):
            if st.button("🎯 Assess Risk", use_container_width=True, key="btn_quick_risk"):
                st.session_state["pending_copilot_prompt"] = "Help me determine my investment risk tolerance and build a risk profile."
            if st.button("🏷️ Categorize", use_container_width=True, key="btn_quick_cat"):
                st.session_state["pending_copilot_prompt"] = "Categorize any uncategorized transactions using AI."
            if st.button("⚖️ Check Drift", use_container_width=True, key="btn_quick_drift"):
                st.session_state["pending_copilot_prompt"] = "Review my current portfolio balance against my target allocation and risk profile."
            if st.button("💡 App Guide", use_container_width=True, key="btn_quick_guide"):
                st.session_state["pending_copilot_prompt"] = "How do I configure bank connections and use this app?"
            st.divider()
            if st.button("🗑️ Clear Chat", use_container_width=True, key="btn_clear_copilot"):
                st.session_state.copilot_history = []
                st.rerun()

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
                if st.button("Process File", type="primary", use_container_width=True, key="btn_process_copilot_file"):
                    st.session_state.copilot_history.append(
                        {"role": "user", "content": f"Uploaded file: `{uploaded_file.name}`"})
                    st.session_state.copilot_is_thinking = True
                    st.session_state.copilot_thread_result = None

                    bytes_data = uploaded_file.read()
                    file_info = [
                        {"name": uploaded_file.name, "bytes": bytes_data}]

                    t = threading.Thread(
                        target=_copilot_worker,
                        args=(f"I have uploaded file: {uploaded_file.name}", st.session_state.copilot_history.copy(
                        ), st.session_state, file_info)
                    )
                    add_script_run_ctx(t)
                    t.start()
                    st.rerun()

    # Render the auto-refreshing history
    render_chat_history()

    # Handle pending prompt from quick action buttons
    prompt_to_run = None
    if "pending_copilot_prompt" in st.session_state:
        prompt_to_run = st.session_state.pop("pending_copilot_prompt")

    # Chat input in sidebar
    user_input = st.sidebar.chat_input(
        "Ask Copilot anything...", key="copilot_chat_input") or prompt_to_run

    if user_input:
        st.session_state.copilot_history.append(
            {"role": "user", "content": user_input})
        st.session_state.copilot_is_thinking = True
        st.session_state.copilot_thread_result = None

        t = threading.Thread(
            target=_copilot_worker,
            args=(user_input, st.session_state.copilot_history.copy(),
                  st.session_state)
        )
        add_script_run_ctx(t)
        t.start()
        st.rerun()
