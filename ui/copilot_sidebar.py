import time
import streamlit as st
from agent import copilot_worker


@st.fragment(run_every=1.0)
def render_copilot_sidebar(settings_page=None) -> None:
    """Renders the decoupled Copilot sidebar assistant with background execution."""
    if "copilot_history" not in st.session_state:
        st.session_state.copilot_history = []

    # Sticky sidebar header: title, actions, and file import
    header_container = st.container(key="sticky_sidebar_header")
    with header_container:
        st.markdown(
            "<h3 style='margin-top: 0.2rem; margin-bottom: 0.8rem;'>Personal Finance Assistant</h3>",
            unsafe_allow_html=True,
        )

        col_acts, col_files = st.columns(2)
        with col_acts:
            with st.popover("⚡ Actions", use_container_width=True):
                if st.button("🎯 Assess Risk", use_container_width=True):
                    st.session_state["pending_copilot_prompt"] = "Help me determine my investment risk tolerance and build a risk profile."
                    st.rerun(scope="app")
                if st.button("🏷️ Categorize", use_container_width=True):
                    st.session_state["pending_copilot_prompt"] = "Categorize any uncategorized transactions using AI."
                    st.rerun(scope="app")
                if st.button("⚖️ Check Drift", use_container_width=True):
                    st.session_state["pending_copilot_prompt"] = "Review my current portfolio balance against my target allocation and risk profile."
                    st.rerun(scope="app")
                if st.button("💡 App Guide", use_container_width=True):
                    st.session_state["pending_copilot_prompt"] = "How do I configure bank connections and use this app?"
                    st.rerun(scope="app")
                st.divider()
                if st.button("🗑️ Clear Chat", use_container_width=True):
                    curr_job_id = st.session_state.pop("copilot_job_id", None)
                    if curr_job_id:
                        copilot_worker.remove_job(curr_job_id)
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
                    if st.button("Process File", type="primary", use_container_width=True):
                        uploaded_file_to_process = uploaded_file

    active_job_id = st.session_state.get("copilot_job_id")
    active_job = copilot_worker.get_job(active_job_id) if active_job_id else None
    active_snapshot = active_job.get_snapshot() if active_job else None

    # Dedicated scrollable chat history panel
    history_container = st.container(height=520, border=True)
    with history_container:
        if not st.session_state.copilot_history and not active_snapshot:
            st.info("Local AI assistant for queries, risk profiling, file parsing & app control.")

        for msg in st.session_state.copilot_history:
            role = msg.get("role", "assistant")
            avatar_map = {"user": "👤", "assistant": "🤖"}
            with st.chat_message(role, avatar=avatar_map.get(role)):
                st.markdown(msg.get("content", ""))
                if msg.get("figure"):
                    st.plotly_chart(msg["figure"], use_container_width=True, theme=None)
                if msg.get("df") is not None and not msg["df"].empty:
                    st.dataframe(msg["df"], use_container_width=True, hide_index=True)
                if msg.get("sql"):
                    with st.expander("Generated SQL"):
                        st.code(msg["sql"], language="sql")

        # Render ongoing background execution
        if active_snapshot:
            with st.chat_message("assistant", avatar="🤖"):
                if active_snapshot["status"] == "running":
                    if active_snapshot["accumulated_text"]:
                        st.markdown(active_snapshot["accumulated_text"])
                    else:
                        st.markdown("💭 *Copilot is analyzing in the background...*")
                elif active_snapshot["status"] == "error":
                    st.error(f"❌ Error: {active_snapshot['error']}")

    # Handle completion of background job
    if active_snapshot and active_snapshot["status"] in ("completed", "error"):
        if active_snapshot["status"] == "completed":
            final_msg = {
                "role": "assistant",
                "content": active_snapshot["accumulated_text"] or "Analysis complete.",
                "figure": active_snapshot["figure"],
                "df": active_snapshot["df"],
                "sql": active_snapshot["sql"],
            }
            if active_snapshot.get("form_request"):
                st.session_state["pending_form"] = active_snapshot["form_request"]
            st.session_state.copilot_history.append(final_msg)
        elif active_snapshot["status"] == "error":
            st.session_state.copilot_history.append({
                "role": "assistant",
                "content": f"⚠️ An error occurred: {active_snapshot['error']}",
            })

        if active_job_id:
            copilot_worker.remove_job(active_job_id)
        st.session_state.pop("copilot_job_id", None)
        st.rerun(scope="app")

    # User input and trigger
    prompt_to_run = st.session_state.pop("pending_copilot_prompt", None)
    user_input = st.chat_input("Ask Copilot anything...", key="copilot_chat_input") or prompt_to_run

    if uploaded_file_to_process:
        user_msg = f"Uploaded file: `{uploaded_file_to_process.name}`"
        st.session_state.copilot_history.append({"role": "user", "content": user_msg})
        bytes_data = uploaded_file_to_process.read()
        file_info = [{"name": uploaded_file_to_process.name, "bytes": bytes_data}]
        job_id = copilot_worker.start_job(
            f"I have uploaded file: {uploaded_file_to_process.name}",
            history=st.session_state.copilot_history.copy(),
            uploaded_files=file_info,
        )
        st.session_state["copilot_job_id"] = job_id
        st.rerun(scope="app")

    elif user_input:
        st.session_state.copilot_history.append({"role": "user", "content": user_input})
        job_id = copilot_worker.start_job(
            user_input,
            history=st.session_state.copilot_history.copy(),
        )
        st.session_state["copilot_job_id"] = job_id
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

