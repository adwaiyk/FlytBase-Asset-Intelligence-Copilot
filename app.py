"""Streamlit UI: login per user, private conversations, inline generative UI.

Run: streamlit run app.py
"""
from datetime import date

import streamlit as st

from copilot import config
from copilot.agent import Agent
from copilot.data import load
from copilot.engine import Engine
from copilot.render import render_sources, render_visual
from copilot.store import Store

st.set_page_config(page_title="WellWise · Asset Intelligence Copilot", page_icon="🛢️", layout="wide")


@st.cache_resource(show_spinner="Loading oil-field data, manuals and reports…")
def boot():
    data = load()
    store = Store()
    store.seed_users(data.users, config.DEFAULT_PASSWORD)
    eng = Engine(data, store)
    return data, store, eng, Agent(eng)


data, store, eng, agent = boot()

# ------------------------------------------------------------------ authentication
token = st.session_state.get("token") or st.query_params.get("t")
user = store.user_for_token(token)
if not user:
    st.title("🛢️ WellWise · Asset Intelligence Copilot")
    st.caption("Sign in as one of the people in the field. Each person's conversations are private.")
    users = store.list_users()
    with st.form("login"):
        uid = st.selectbox("User", [u["user_id"] for u in users],
                           format_func=lambda i: next(f"{u['name']} — {u['role'].replace('_', ' ')} ({u['team_id']})"
                                                      for u in users if u["user_id"] == i))
        pw = st.text_input("Password", type="password", help="Demo default is set by COPILOT_DEFAULT_PASSWORD")
        if st.form_submit_button("Sign in", type="primary"):
            t = store.login(uid, pw)
            if t:
                st.session_state.token = t
                st.query_params["t"] = t
                st.rerun()
            st.error("Wrong password")
    st.stop()

st.session_state.token = token

# ------------------------------------------------------------------ sidebar: account + private chats
with st.sidebar:
    st.markdown(f"### 👤 {user['name']}")
    st.caption(f"{user['role'].replace('_', ' ')} · {data.teams.get(user['team_id'], {}).get('name', user['team_id'])}")
    c1, c2 = st.columns(2)
    if c1.button("Sign out", use_container_width=True):
        store.logout(token)
        st.session_state.clear()
        st.query_params.clear()
        st.rerun()
    with st.popover("Password", use_container_width=True):
        old = st.text_input("Current", type="password", key="pw_old")
        new = st.text_input("New (6+ chars)", type="password", key="pw_new")
        if st.button("Change"):
            st.success("Changed") if store.change_password(user["user_id"], old, new) else st.error("Not changed")

    st.divider()
    st.markdown("**Conversations** (private)")
    sim = st.date_input("Session date for a new chat", value=date.today(),
                        help="Lets you simulate 'yesterday' / 'day 2' in a same-day demo")
    if st.button("➕ New chat", use_container_width=True, type="primary"):
        st.session_state.conv = store.new_conversation(user["user_id"], str(sim))
        st.rerun()
    convs = store.conversations(user["user_id"])
    if not convs:
        st.session_state.conv = store.new_conversation(user["user_id"], str(sim))
        convs = store.conversations(user["user_id"])
    cur = st.session_state.get("conv")
    if cur not in [c["conv_id"] for c in convs]:
        cur = st.session_state.conv = convs[0]["conv_id"]
    for c in convs[:25]:
        label = f"{'▶ ' if c['conv_id'] == cur else ''}{c['title']} · {c['sim_date']}"
        if st.button(label, key=c["conv_id"], use_container_width=True):
            st.session_state.conv = c["conv_id"]
            st.rerun()

    st.divider()
    with st.expander("Data & rules loaded"):
        r = data.load_report
        st.caption(f"Today = **{r['as_of']}** · {r['wells']} wells · {r['inspections']:,} inspections · "
                   f"{r['repairs']:,} repairs · {r['reports']:,} reports · {r['notes']} notes")
        st.caption("Areas: " + ", ".join(r["areas"].values()))
        for k, scope, val in r["rules"]:
            st.caption(f"`{k}` [{scope}] = {val:g}")
    with st.expander("Demo admin"):
        st.caption("Clears all feedback and every user's conversations (to re-run scenarios).")
        if st.button("Reset memory"):
            store.reset_memory()
            eng.refresh(force=True)
            st.session_state.pop("conv", None)
            st.rerun()

conv = store.conversation(user["user_id"], st.session_state.conv)

# ------------------------------------------------------------------ chat
st.markdown(f"#### 🛢️ WellWise · {conv['title']}  <span style='font-size:0.7em;color:gray'>session date {conv['sim_date']} · "
            f"data as of {data.load_report['as_of']}</span>", unsafe_allow_html=True)


def show_assistant(m, key):
    p = m.get("payload") or {}
    for w in p.get("memory_writes") or []:
        icon = "✅" if w["status"] == "applied" else "⚠️"
        st.caption(f"{icon} Remembered as {w['id']} ({w['kind'].replace('_', ' ')}, {w['status']}) — shared with all users")
    st.markdown(m["content"] or "_(no answer)_")
    for c in p.get("conflicts") or []:
        st.warning(f"Conflict: {c}")
    render_visual(p.get("visual"), key)
    render_sources(p.get("sources"), key)
    if p.get("unverified_ids"):
        st.caption("⚠️ Not found in tool results: " + ", ".join(p["unverified_ids"]))
    if p.get("trace"):
        with st.expander("How I answered"):
            for t in p["trace"]:
                st.code(f"{t['tool']}({t.get('args')})" + (f"  → error: {t['error']}" if t.get("error") else ""),
                        language="python")
            st.caption(f"model: {p.get('model')}")


for i, m in enumerate(store.messages(user["user_id"], conv["conv_id"])):
    with st.chat_message(m["role"], avatar="🛢️" if m["role"] == "assistant" else "👤"):
        if m["role"] == "assistant":
            show_assistant(m, f"{conv['conv_id']}-{i}")
        else:
            st.markdown(m["content"])

if not store.messages(user["user_id"], conv["conv_id"]):
    st.caption("Try: *Is WELL-0001 producing oil right now?* · *Which wells in Northeast Block 8 are not producing, and "
               "why? Show a table.* · *Show a heatmap of 2026 spills by area and month.*")

if q := st.chat_input("Ask about wells, inspections, spills, repairs, compliance… or tell me a correction"):
    with st.chat_message("user", avatar="👤"):
        st.markdown(q)
    with st.chat_message("assistant", avatar="🛢️"):
        with st.spinner("Checking the records…"):
            try:
                out = agent.run(user, conv, q)
            except Exception as e:
                st.error(f"Copilot error: {e}")
                st.stop()
        show_assistant({"content": out["content"], "payload": out}, f"{conv['conv_id']}-new")
    st.rerun()
