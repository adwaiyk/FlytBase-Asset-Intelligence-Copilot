"""Generative UI renderer: a fixed catalog of components (A2UI-style). The agent
chooses component + result handle; the rows come from the tool result, never
from LLM text."""
from __future__ import annotations

import pydeck as pdk
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from ui_polish import style_plotly_figure, render_well_status_card

OK, BAD, AIR, WELL = "#10B981", "#EF4444", "#94A3B8", "#F59E0B"


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
    if "producing" not in r and "is_producing" not in r:
        return _table(rows, title, v, key)
    render_well_status_card(r)
    # If there are open repairs, notes, or observations, show them neatly below
    extra_items = []
    if r.get("observation"):
        extra_items.append(f"🔍 **Observation:** {r['observation']}")
    for op in r.get("open_repairs") or []:
        extra_items.append(f"🔧 **Open Repair:** {op}")
    for ctx in r.get("context") or []:
        extra_items.append(f"📝 {ctx}")
    if extra_items:
        with st.container():
            for item in extra_items:
                st.caption(item)


def _table(rows, title, v, key):
    df = pd.DataFrame(rows)
    cols = [c for c in (v.get("columns") or []) if c in df.columns] or list(df.columns)
    df = df[cols]
    if "producing" in df:
        df["producing"] = df["producing"].map({True: "yes", False: "no"})
    if title:
        st.markdown(f"**📋 {title}**")
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
                                 mode="lines+markers", line=dict(color=colors.get(s, "#38BDF8"), width=2.5)))
    if "producing" in df:
        off = df[~df["producing"].astype(bool)]
        fig.add_trace(go.Scatter(x=off[x], y=off[series[0]], mode="markers", name="not producing",
                                 marker=dict(color=BAD, size=14, symbol="x")))
        for xv in off[x]:
            fig.add_vrect(x0=xv - pd.Timedelta(days=3), x1=xv + pd.Timedelta(days=3), fillcolor=BAD, opacity=0.12,
                          line_width=0)
    fig.update_layout(height=380, yaxis_title="°C")
    fig = style_plotly_figure(fig, title)
    st.plotly_chart(fig, use_container_width=True, key=f"l{key}")


def _bar(rows, title, v, key):
    df = pd.DataFrame(rows)
    h = v.get("hints", {})
    x = h.get("x") if h.get("x") in df else df.columns[0]
    y = h.get("y") if h.get("y") in df else next(c for c in df.columns if df[c].dtype.kind in "fi")
    color = "well_type" if "well_type" in df else None
    fig = px.bar(df, x=x, y=y, color=color, text=y, title=title,
                 color_discrete_sequence=["#F59E0B", "#38BDF8", "#EF4444"])
    fig.update_layout(height=380)
    fig = style_plotly_figure(fig, title)
    st.plotly_chart(fig, use_container_width=True, key=f"b{key}")


def _map(rows, title, v, key):
    df = pd.DataFrame(rows)
    lat_col = "latitude" if "latitude" in df.columns else ("lat" if "lat" in df.columns else None)
    lon_col = "longitude" if "longitude" in df.columns else ("lon" if "lon" in df.columns else None)
    if not lat_col or not lon_col:
        return _table(rows, title, v, key)
    df = df.dropna(subset=[lat_col, lon_col])
    if df.empty:
        return _table(rows, title, v, key)

    if title:
        st.markdown(f"**🗺️ {title}**")

    # Try modern dark PyDeck map
    rendered_deck = False
    try:
        df["_lat"] = df[lat_col].astype(float)
        df["_lon"] = df[lon_col].astype(float)
        layer = pdk.Layer(
            "ScatterplotLayer",
            data=df,
            get_position="[_lon, _lat]",
            get_fill_color="[245, 158, 11, 220]",
            get_line_color="[255, 255, 255, 255]",
            line_width_min_pixels=2,
            get_radius=400,
            pickable=True,
        )
        view_state = pdk.ViewState(
            latitude=float(df["_lat"].mean()),
            longitude=float(df["_lon"].mean()),
            zoom=11.2,
            pitch=30,
        )
        tooltip_fields = []
        if "asset_id" in df:
            tooltip_fields.append("Asset: {asset_id}")
        if "date" in df:
            tooltip_fields.append("Date: {date}")
        if "volume_bbl" in df:
            tooltip_fields.append("Volume: {volume_bbl} bbl")
        if "spill_class" in df:
            tooltip_fields.append("Class: {spill_class}")
        tt_text = "\n".join(tooltip_fields) if tooltip_fields else "Asset: {asset_id}"

        st.pydeck_chart(pdk.Deck(
            map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
            initial_view_state=view_state,
            layers=[layer],
            tooltip={"text": tt_text}
        ))
        rendered_deck = True
    except Exception:
        pass

    if not rendered_deck:
        hover = [c for c in ("asset_id", "date", "volume_bbl", "spill_class", "delta_c", "reason") if c in df]
        size = "volume_bbl" if "volume_bbl" in df else None
        fig = px.scatter_map(df, lat=lat_col, lon=lon_col, hover_name="asset_id" if "asset_id" in df else None,
                             hover_data=hover, size=size, size_max=22, zoom=11, title=title,
                             color="spill_class" if "spill_class" in df else None,
                             text="asset_id" if "asset_id" in df else None)
        fig.update_traces(marker=dict(sizemin=10))
        fig.update_layout(map_style="carto-darkmatter", height=440, margin=dict(l=0, r=0, t=40, b=0))
        st.plotly_chart(fig, use_container_width=True, key=f"m{key}")

    _table(rows, "Asset Coordinates & Records",
           {"columns": [c for c in ("asset_id", "date", "volume_bbl", "spill_class", lat_col, lon_col) if c in df]},
           key + "m")


def _heatmap(rows, title, v, key):
    df = pd.DataFrame(rows)
    idx = v.get("hints", {}).get("rows_field", df.columns[0])
    df = df.set_index(idx)
    total = df.pop("Total") if "Total" in df else None
    fig = px.imshow(df, text_auto=True, aspect="auto", color_continuous_scale="YlOrRd", title=title)
    fig.update_layout(height=120 + 45 * len(df))
    fig = style_plotly_figure(fig, title)
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

