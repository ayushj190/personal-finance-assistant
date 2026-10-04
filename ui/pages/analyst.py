import streamlit as st

from agent.analyst import query_analyst


def render():
    st.title("AI Financial Analyst")
    st.markdown("Ask natural language questions about your transactions, spending patterns, net worth, or portfolio.")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # Quick prompt buttons
    st.markdown("**Example Questions:**")
    q_cols = st.columns(3)
    preset_q = None
    with q_cols[0]:
        if st.button("🛒 Groceries spend last month?"):
            preset_q = "How much did I spend on groceries last month?"
    with q_cols[1]:
        if st.button("📊 Portfolio allocation by asset type?"):
            preset_q = "What is my current portfolio allocation by asset type?"
    with q_cols[2]:
        if st.button("💳 Top 5 merchants by total spend?"):
            preset_q = "Top 5 merchants by total spend this year"

    # Display chat history
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("figure"):
                st.plotly_chart(msg["figure"], use_container_width=True)
            if msg.get("df") is not None and not msg["df"].empty:
                st.dataframe(msg["df"], use_container_width=True, hide_index=True)
            if msg.get("sql"):
                with st.expander("View Generated SQL"):
                    st.code(msg["sql"], language="sql")

    # Chat input
    user_prompt = st.chat_input("Ask about your finances...") or preset_q

    if user_prompt:
        st.session_state.chat_history.append({"role": "user", "content": user_prompt})
        with st.chat_message("user"):
            st.markdown(user_prompt)

        with st.chat_message("assistant"):
            with st.spinner("Analyzing financial data..."):
                result = query_analyst(user_prompt)
                st.markdown(result["answer"])
                if result.get("figure"):
                    st.plotly_chart(result["figure"], use_container_width=True)
                if result.get("df") is not None and not result["df"].empty:
                    st.dataframe(result["df"], use_container_width=True, hide_index=True)
                if result.get("sql"):
                    with st.expander("View Generated SQL"):
                        st.code(result["sql"], language="sql")

                st.session_state.chat_history.append(
                    {
                        "role": "assistant",
                        "content": result["answer"],
                        "figure": result.get("figure"),
                        "df": result.get("df"),
                        "sql": result.get("sql"),
                    }
                )
