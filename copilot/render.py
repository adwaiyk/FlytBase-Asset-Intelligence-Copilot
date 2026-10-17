"""Generative UI renderer: a fixed catalog of components (A2UI-style). The agent
chooses component + result handle; the rows come from the tool result, never
from LLM text."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

OK, BAD, AIR, WELL = "#2E7D32", "#C62828", "#90A4AE", "#E65100"


def render_visual(v: dict, key: str):
    if not v or not v.get("rows"):
        return
    comp, rows, title = v["component"], v["rows"], v.get("title") or ""
    try:
        {"status_card": _card, "table": _table, "line_chart": _line, "bar_chart": _bar, "map": _map,
         "heatmap": _heatmap}.get(comp, _table)(rows, title, v, key)
    except Exception as e:  # never break the chat: fall back to a table
        st.caption(f"({comp} could not be drawn: {e}; showing the rows)")
        _table(rows, title, v, key)


def _card(rows, title, v, key):
    r = rows[0]
    if "producing" not in r:
        return _table(rows, title, v, key)
    ok = r["producing"]
    with st.container(border=True):
        c1, c2 = st.columns([3, 2])
        c1.markdown(f"### {'🟢' if ok else '🔴'} {r['asset_id']} · {'Producing oil' if ok else 'Not producing oil'}")
        c1.caption(f"{r.get('name', '')} · {r.get('well_type')} · {r.get('area')}")
        c2.metric("Wellhead above air", f"{r['delta_c']} °C", f"limit {r['threshold_c']:g} °C", delta_color="off")
        a, b, c = st.columns(3)
        a.markdown(f"**Last inspection**  \n{r['last_inspection_id']}  \n{r['last_inspected']} · {r['method']} · {r['inspector']}")
        stale = r.get("recorded_status_out_of_date")
        b.markdown(f"**Recorded status**  \n`{r['recorded_status']}`" + ("  \n:red[out of date]" if stale else "  \n:green[matches]"))
        c.markdown(f"**Readings**  \nwellhead {r['wellhead_temp_c']} °C  \nair {r['ambient_temp_c']} °C")
        if r.get("reason"):
            st.markdown(f"**Reason:** {r['reason']}")
        if r.get("observation"):
            st.markdown(f"**Inspector observation:** “{r['observation']}” — suggest a field check")
        if r.get("corrected"):
            st.info(f"Reading corrected ({r['corrected']}); original wellhead {r.get('original_wellhead_temp_c')} °C kept.")
        for o in r.get("open_repairs") or []:
            st.markdown(f"🔧 Open repair: {o}")
        for c_ in r.get("context") or []:
            st.markdown(f"📝 {c_}")
        for c_ in r.get("conflicts") or []:
            st.warning(c_)
        st.caption(f"Rule: {r.get('threshold_source')}")


def _table(rows, title, v, key):
    df = pd.DataFrame(rows)
    cols = [c for c in (v.get("columns") or []) if c in df.columns] or list(df.columns)
    df = df[cols]
    if "producing" in df:
        df["producing"] = df["producing"].map({True: "yes", False: "no"})
    st.markdown(f"**{title}**")
    st.dataframe(df, hide_index=True, use_container_width=True, key=f"t{key}")


def _line(rows, title, v, key):
    df = pd.DataFrame(rows)
    h = v.get("hints", {})
    x = h.get("x", "date")
    series = h.get("series") or [c for c in df.columns if df[c].dtype.kind in "fi"][:2]
    if "t" in df:
        df["_x"] = pd.to_datetime(df["t"])
        x = "_x"
    fig = go.Figure()
    colors = {"wellhead_temp_c": WELL, "ambient_temp_c": AIR}
    for s in series:
        fig.add_trace(go.Scatter(x=df[x], y=df[s], name=s.replace("_temp_c", "").replace("_", " ") + " °C",
                                 mode="lines+markers", line=dict(color=colors.get(s), width=2)))
    if "producing" in df:
        off = df[~df["producing"].astype(bool)]
        fig.add_trace(go.Scatter(x=off[x], y=off[series[0]], mode="markers", name="not producing",
                                 marker=dict(color=BAD, size=14, symbol="x")))
        for xv in off[x]:
            fig.add_vrect(x0=xv - pd.Timedelta(days=3), x1=xv + pd.Timedelta(days=3), fillcolor=BAD, opacity=0.08,
                          line_width=0)
    fig.update_layout(title=title, height=380, margin=dict(l=10, r=10, t=40, b=10), yaxis_title="°C",
                      legend=dict(orientation="h", y=-0.2))
    st.plotly_chart(fig, use_container_width=True, key=f"l{key}")


def _bar(rows, title, v, key):
    df = pd.DataFrame(rows)
    h = v.get("hints", {})
    x = h.get("x") if h.get("x") in df else df.columns[0]
    y = h.get("y") if h.get("y") in df else next(c for c in df.columns if df[c].dtype.kind in "fi")
    color = "well_type" if "well_type" in df else None
    fig = px.bar(df, x=x, y=y, color=color, text=y, title=title,
                 color_discrete_sequence=["#1565C0", "#EF6C00", "#6A1B9A"])
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig, use_container_width=True, key=f"b{key}")


def _map(rows, title, v, key):
    df = pd.DataFrame(rows).dropna(subset=["lat", "lon"])
    hover = [c for c in ("asset_id", "date", "volume_bbl", "spill_class", "delta_c", "reason") if c in df]
    size = "volume_bbl" if "volume_bbl" in df else None
    fig = px.scatter_map(df, lat="lat", lon="lon", hover_name="asset_id" if "asset_id" in df else None,
                         hover_data=hover, size=size, size_max=22, zoom=11, title=title,
                         color="spill_class" if "spill_class" in df else None,
                         text="asset_id" if "asset_id" in df else None)
    fig.update_traces(marker=dict(sizemin=10))
    fig.update_layout(map_style="open-street-map", height=440, margin=dict(l=0, r=0, t=40, b=0))
    st.plotly_chart(fig, use_container_width=True, key=f"m{key}")
    _table(rows, "Pins", {"columns": [c for c in ("asset_id", "date", "volume_bbl", "spill_class", "lat", "lon") if c in df]}, key + "m")


def _heatmap(rows, title, v, key):
    df = pd.DataFrame(rows)
    idx = v.get("hints", {}).get("rows_field", df.columns[0])
    df = df.set_index(idx)
    total = df.pop("Total") if "Total" in df else None
    fig = px.imshow(df, text_auto=True, aspect="auto", color_continuous_scale="OrRd", title=title)
    fig.update_layout(height=120 + 45 * len(df), margin=dict(l=10, r=10, t=40, b=10))
    st.plotly_chart(fig, use_container_width=True, key=f"h{key}")
    if total is not None:
        st.caption("Totals: " + " · ".join(f"{i}: **{t}**" for i, t in total.items()))


def render_sources(sources: list[dict], key: str):
    if not sources:
        return
    with st.expander(f"Evidence ({len(sources)} sources)"):
        for s in sources:
            k = s.get("kind")
            if k == "doc":
                st.markdown(f"📘 **{s.get('doc')}** § {s.get('section', '')}  \n> {str(s.get('quote', ''))[:300]}")
            elif k in ("note", "feedback"):
                st.markdown(f"📝 **{s.get('id')}** by {s.get('author')}" + (f" [{s.get('status')}]" if s.get("status") else "")
                            + f": {s.get('text', '')}")
            else:
                st.markdown(f"🔎 **{s.get('id', s.get('doc'))}** · {k}" + (f" · {s.get('date')}" if s.get("date") else "")
                            + (f" · `{s.get('file')}`" if s.get("file") else ""))
