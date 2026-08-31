import streamlit as st

from components import render_empty_state, render_history, render_live_answer, render_sidebar

st.set_page_config(page_title="FinSight", page_icon="📊")
st.title("FinSight")
st.caption(
    "Ask about the 10-K filings of Apple, Microsoft, and NVIDIA. Quantitative "
    "questions hit the knowledge graph, narrative ones the vector store. Name a "
    "fiscal year and the filings for that year are the ones that get read."
)

render_sidebar()

if "history" not in st.session_state:
    st.session_state.history = []

question = st.chat_input("e.g. What was Apple's net income?", submit_mode="disable")
if question is None:
    question = st.session_state.pop("pending", None)

if not st.session_state.history and not question:
    render_empty_state()

render_history(st.session_state.history)

if question:
    answer, meta = render_live_answer(question)
    st.session_state.history.append(
        {
            "question": question,
            "answer": answer,
            "route": meta.get("route", "?"),
            "year": meta.get("year"),
        }
    )
