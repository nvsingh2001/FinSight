import requests
import streamlit as st

from api_client import ask_stream, load_stats
from config import (
    API_URL,
    ASSISTANT_AVATAR,
    ROUTE_BADGE_COLORS,
    ROUTE_LABELS,
    SAMPLE_QUESTIONS,
    SUGGESTIONS,
)


def answered_via(route, year):
    label = ROUTE_LABELS.get(route, route or "?")
    color = ROUTE_BADGE_COLORS.get(route, "gray")
    badge = f":{color}-badge[{label}]"
    if year and year != "latest" and route in ("vector", "hybrid"):
        badge += f" · FY{year}"
    return badge


def pick_suggestion():
    choice = st.session_state.suggestion
    if choice:
        st.session_state.pending = SUGGESTIONS[choice]
        st.session_state.suggestion = None


def render_sidebar():
    with st.sidebar:
        st.subheader("Try asking")
        for sample in SAMPLE_QUESTIONS:
            if st.button(sample, width="stretch"):
                st.session_state.pending = sample
        st.caption(f"API: {API_URL}")


def render_empty_state():
    stats = load_stats()
    if stats:
        cols = st.columns(3)
        cols[0].metric("Companies", stats["companies"], border=True)
        cols[1].metric(
            "Filings indexed",
            stats["filings"],
            border=True,
            help=f"{stats['chunks']:,} passages embedded for retrieval",
        )
        cols[2].metric(
            "Fiscal years per company",
            stats["fiscal_years"],
            border=True,
            help=f"{stats['first_year']}-{stats['last_year']} across the three",
        )

    st.pills(
        "Try one of these",
        list(SUGGESTIONS),
        key="suggestion",
        on_change=pick_suggestion,
    )


def render_history(history):
    for entry in history:
        with st.chat_message("user"):
            st.write(entry["question"])
        with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
            st.write(entry["answer"])
            st.caption(answered_via(entry["route"], entry.get("year")))


def render_live_answer(question):
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
        status = st.status("thinking...", expanded=False)
        box = st.empty()
        buf, meta = "", {}
        try:
            for ev in ask_stream(question):
                if ev["type"] == "progress":
                    status.update(label=ev["stage"])
                elif ev["type"] == "token":
                    buf += ev["text"]
                    box.markdown(buf + "▌")
                elif ev["type"] == "revising":
                    buf = ""
                    box.empty()
                    status.update(label="first draft rejected, revising...")
                elif ev["type"] == "done":
                    meta = ev
        except requests.RequestException:
            st.error(f"Could not reach the FinSight API at {API_URL}. Is it running?")
            st.stop()
        box.markdown(buf)
        status.update(
            state="complete",
            label=answered_via(meta.get("route"), meta.get("year")),
        )
    return buf, meta
