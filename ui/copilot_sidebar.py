import streamlit as st
from agent.copilot import run_copilot

def render_copilot_sidebar(settings_page=None) -> None:
    """Renders the persistent Copilot 365 sidebar assistant."""
    if "copilot_history" not in st.session_state:
        st.session_state.copilot_history = []


    # Quick actions and File dropzone side by side
    header_container = st.container(key="sticky_sidebar_header")
    with header_container:
        st.markdown("<h3 style='margin-top: 0.2rem; margin-bottom: 1rem;'>Personal Finance Assistant</h3>", unsafe_allow_html=True)
            
        col_acts, col_files = st.columns(2)
        with col_acts:
            with st.popover("⚡ Actions", use_container_width=True):
                if st.button("🎯 Assess Risk", use_container_width=True):
                    st.session_state["pending_copilot_prompt"] = "Help me determine my investment risk tolerance and build a risk profile."
                if st.button("🏷️ Categorize", use_container_width=True):
                    st.session_state["pending_copilot_prompt"] = "Categorize any uncategorized transactions using AI."
                if st.button("⚖️ Check Drift", use_container_width=True):
                    st.session_state["pending_copilot_prompt"] = "Review my current portfolio balance against my target allocation and risk profile."
                if st.button("💡 App Guide", use_container_width=True):
                    st.session_state["pending_copilot_prompt"] = "How do I configure bank connections and use this app?"
                st.divider()
                if st.button("🗑️ Clear Chat", use_container_width=True):
                    st.session_state.copilot_history = []
                    st.rerun()

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

    history_container = st.container(border=False)
    with history_container:
        if not st.session_state.copilot_history:
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


    prompt_to_run = None
    if "pending_copilot_prompt" in st.session_state:
        prompt_to_run = st.session_state.pop("pending_copilot_prompt")

    user_input = st.sidebar.chat_input("Ask Copilot anything...", key="copilot_chat_input") or prompt_to_run

    if uploaded_file_to_process:
        # File upload logic
        user_msg = f"Uploaded file: `{uploaded_file_to_process.name}`"
        st.session_state.copilot_history.append({"role": "user", "content": user_msg})
        with history_container:
            with st.chat_message("user", avatar="👤"):
                st.markdown(user_msg)
                
            with st.chat_message("assistant", avatar="🤖"):
                with st.spinner("Processing file..."):
                    bytes_data = uploaded_file_to_process.read()
                    file_info = [{"name": uploaded_file_to_process.name, "bytes": bytes_data}]
                    response = run_copilot(
                        f"I have uploaded file: {uploaded_file_to_process.name}", 
                        history=st.session_state.copilot_history.copy(), 
                        uploaded_files=file_info
                    )
                    
                    content = "".join(response.get("stream", []))
                    st.markdown(content)
                    
                    final_msg = {
                        "role": "assistant",
                        "content": content,
                        "figure": response.get("figure"),
                        "df": response.get("df"),
                        "sql": response.get("sql")
                    }
                    if "form_request" in response:
                        st.session_state["pending_form"] = response["form_request"]
                    st.session_state.copilot_history.append(final_msg)

    elif user_input:
        st.session_state.copilot_history.append({"role": "user", "content": user_input})
        
        with history_container:
            with st.chat_message("user", avatar="👤"):
                st.markdown(user_input)
                
            with st.chat_message("assistant", avatar="🤖"):
                response = run_copilot(user_input, history=st.session_state.copilot_history.copy())
                
                # Render tool data immediately if it exists
                if response.get("figure"):
                    st.plotly_chart(response["figure"], use_container_width=True, theme=None)
                if response.get("df") is not None and not response["df"].empty:
                    st.dataframe(response["df"], use_container_width=True, hide_index=True)
                if response.get("sql"):
                    with st.expander("Generated SQL"):
                        st.code(response["sql"], language="sql")
                
                # Stream text
                stream_gen = response.get("stream", [])
                content = st.write_stream(stream_gen)
                
                final_msg = {
                    "role": "assistant",
                    "content": content,
                    "figure": response.get("figure"),
                    "df": response.get("df"),
                    "sql": response.get("sql")
                }
                if "form_request" in response:
                    st.session_state["pending_form"] = response["form_request"]
                st.session_state.copilot_history.append(final_msg)

    if st.session_state.get("pending_form") == "tax_profile":
        from ui.dialogs import tax_profile_dialog
        tax_profile_dialog()
    elif st.session_state.get("pending_form") == "risk_profile":
        from ui.dialogs import risk_profile_dialog
        risk_profile_dialog()
    elif st.session_state.get("pending_form") == "mortgage_config":
        from ui.dialogs import mortgage_config_dialog
        mortgage_config_dialog()
