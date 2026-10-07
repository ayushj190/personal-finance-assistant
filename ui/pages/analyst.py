import streamlit as st

from agent.copilot import run_copilot
from config import DB_PATH
from db import database


def render():
    st.title("🧠 AI Copilot & Financial Analyst")
    st.markdown("Your private, local AI copilot for natural language analytics, portfolio rebalancing, risk assessment, and app control.")

    conn = database.connect(DB_PATH)
    risk_prof = database.get_latest_risk_profile(conn)
    conn.close()

    # Risk Profile Status Card
    with st.container(border=True):
        col_r1, col_r2, col_r3 = st.columns([2, 2, 1])
        with col_r1:
            st.markdown("#### 🎯 Investment Risk Profile")
            if risk_prof:
                st.markdown(f"**Tolerance:** `{risk_prof['risk_tolerance']}` | **Score:** `{risk_prof['risk_score']}/10`")
                st.caption(f"Last assessed: {risk_prof.get('assessed_date', 'N/A')[:10]}")
            else:
                st.markdown("⚪ *No risk profile established yet.*")
                st.caption("Complete an interactive assessment with Copilot.")
        with col_r2:
            if risk_prof and risk_prof.get("notes"):
                st.caption(f"**Notes:** {risk_prof['notes']}")
            elif risk_prof and risk_prof.get("answers"):
                ans_count = len(risk_prof["answers"])
                st.caption(f"Recorded answers for {ans_count} assessment questions.")
            else:
                st.caption("Copilot will remind you of your risk tolerance and help you maintain target balance.")
        with col_r3:
            if st.button("🎯 Assess / Update Risk Profile", use_container_width=True):
                st.session_state["copilot_page_prompt"] = "Help me assess my investment risk tolerance and update my risk profile."

    if "copilot_history" not in st.session_state:
        st.session_state.copilot_history = []

    # Quick prompt buttons
    st.markdown("**Suggested Questions & Actions:**")
    q_cols = st.columns(4)
    preset_q = None
    with q_cols[0]:
        if st.button("🛒 Groceries spend last month?", use_container_width=True):
            preset_q = "How much did I spend on groceries last month?"
    with q_cols[1]:
        if st.button("📊 Portfolio vs target allocation?", use_container_width=True):
            preset_q = "Review my current portfolio balance against my target allocation and risk profile."
    with q_cols[2]:
        if st.button("🏷️ Categorize transactions", use_container_width=True):
            preset_q = "Categorize any uncategorized transactions using AI."
    with q_cols[3]:
        if st.button("💡 How to configure Open Banking?", use_container_width=True):
            preset_q = "Explain how to set up Enable Banking Open Banking keys and sync my accounts."

    # Display chat history
    for msg in st.session_state.copilot_history:
        with st.chat_message(msg.get("role", "assistant")):
            st.markdown(msg.get("content", ""))
            if msg.get("figure"):
                st.plotly_chart(msg["figure"], use_container_width=True)
            if msg.get("df") is not None and not msg["df"].empty:
                st.dataframe(msg["df"], use_container_width=True, hide_index=True)
            if msg.get("sql"):
                with st.expander("View Generated SQL"):
                    st.code(msg["sql"], language="sql")

    # Chat input
    pending = st.session_state.pop("copilot_page_prompt", None)
    user_prompt = st.chat_input("Ask Copilot anything about your money, settings, or risk...") or preset_q or pending

    if user_prompt:
        st.session_state.copilot_history.append({"role": "user", "content": user_prompt})
        with st.chat_message("user"):
            st.markdown(user_prompt)

        with st.chat_message("assistant"):
            with st.spinner("Copilot analyzing..."):
                result = run_copilot(user_prompt, history=st.session_state.copilot_history)
                st.markdown(result["content"])
                if result.get("figure"):
                    st.plotly_chart(result["figure"], use_container_width=True)
                if result.get("df") is not None and not result["df"].empty:
                    st.dataframe(result["df"], use_container_width=True, hide_index=True)
                if result.get("sql"):
                    with st.expander("View Generated SQL"):
                        st.code(result["sql"], language="sql")

                st.session_state.copilot_history.append(result)

