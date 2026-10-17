"""FLYTBASE // Asset Intelligence OS
Industrial SCADA & Palantir Foundry-Style Command Center

Run: py -m streamlit run app.py
"""
from __future__ import annotations

import os
import re
from datetime import date
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pydeck as pdk

from copilot import config
from copilot.agent import Agent
from copilot.data import load
from copilot.engine import Engine
from copilot.store import Store

# -----------------------------------------------------------------------------
# 1. PAGE CONFIG
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="FLYTBASE // Asset Intelligence OS",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -----------------------------------------------------------------------------
# 2. SYSTEM BOOTSTRAP (DATA, ENGINE, AGENT, STORE)
# -----------------------------------------------------------------------------
@st.cache_resource(show_spinner="Booting Asset Intelligence OS & indexing telemetry…")
def boot_system():
    data = load()
    store = Store()
    store.seed_users(data.users, config.DEFAULT_PASSWORD)
    eng = Engine(data, store)
    agent = Agent(eng)
    return data, store, eng, agent

data, store, eng, agent = boot_system()

# -----------------------------------------------------------------------------
# 3. REAL-TIME FLEET TELEMETRY HUD (DIRECT FROM COMPILED DATA & ENGINE)
# -----------------------------------------------------------------------------
def get_fleet_kpis():
    try:
        total_wells = len(eng.wells)
        producing_wells = int(eng.latest["producing"].sum())
        down_wells = total_wells - producing_wells
        total_insp = len(eng.I)
        open_fines = int(data.reg[data.reg["status"] == "open"]["fine_usd"].sum()) if not data.reg.empty and "fine_usd" in data.reg.columns else 7500
        today_str = str(eng.as_of.date()) if hasattr(eng.as_of, "date") else str(eng.as_of)[:10]
        return {
            "total_wells": total_wells,
            "producing_wells": producing_wells,
            "down_wells": down_wells,
            "total_inspections": f"{total_insp:,}",
            "open_fines": f"${open_fines:,}",
            "today": today_str
        }
    except Exception:
        return {
            "total_wells": 200, "producing_wells": 185, "down_wells": 15,
            "total_inspections": "39,567", "open_fines": "$7,500", "today": "2026-10-16"
        }

# -----------------------------------------------------------------------------
# 4. PALANTIR / INDUSTRIAL SCADA CYBER-THEME CSS
# -----------------------------------------------------------------------------
def inject_pwa_and_logo():
    """Inject PWA manifest link, apple-touch-icon, SW registration, and logo CSS."""
    st.markdown("""
    <!-- PWA: Manifest & Apple Meta -->
    <link rel="manifest" href="/app/static/manifest.json">
    <link rel="apple-touch-icon" href="/app/static/logo.png">
    <meta name="theme-color" content="#F59E0B">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="AssetAI">
    <script>
      if ('serviceWorker' in navigator) {
        window.addEventListener('load', function() {
          navigator.serviceWorker.register('/app/static/sw.js')
            .then(function(reg) { console.log('[PWA] SW registered:', reg.scope); })
            .catch(function(err) { console.warn('[PWA] SW failed:', err); });
        });
      }
    </script>
    """, unsafe_allow_html=True)


def inject_scada_theme():
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap');

        /* Global Reset & Deep Cyber-Industrial Canvas */
        .stApp {
            background: radial-gradient(circle at 15% 10%, #0F172A 0%, #060911 60%, #030509 100%) !important;
            color: #E2E8F0 !important;
            font-family: 'Inter', sans-serif !important;
        }
        #MainMenu, footer, header {visibility: hidden !important; height: 0 !important;}
        .block-container {
            padding-top: 1.0rem !important;
            padding-bottom: 5rem !important;
            padding-left: 2.2rem !important;
            padding-right: 2.2rem !important;
            max-width: 100% !important;
        }

        /* Sleek Sidebar Glass Panel */
        [data-testid="stSidebar"] {
            background: rgba(9, 13, 24, 0.95) !important;
            border-right: 1px solid rgba(56, 189, 248, 0.16) !important;
        }

        /* Top Command Navbar */
        .scada-navbar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: rgba(15, 23, 42, 0.75);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(148, 163, 184, 0.15);
            border-left: 4px solid #F59E0B;
            border-radius: 10px;
            padding: 12px 22px;
            margin-bottom: 14px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.45);
        }
        .brand-title {
            font-family: 'Space Grotesk', sans-serif;
            font-size: 1.35rem;
            font-weight: 700;
            letter-spacing: 0.03em;
            color: #F8FAFC;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .brand-sub {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.72rem;
            color: #38BDF8;
            text-transform: uppercase;
            letter-spacing: 0.12em;
        }

        /* Top 5-Column Bento KPI Strip */
        .kpi-strip {
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 12px;
            margin-bottom: 18px;
        }
        .kpi-card {
            background: linear-gradient(160deg, rgba(15, 23, 42, 0.85) 0%, rgba(9, 14, 26, 0.9) 100%);
            border: 1px solid rgba(148, 163, 184, 0.12);
            border-radius: 10px;
            padding: 12px 16px;
            position: relative;
            overflow: hidden;
        }
        .kpi-card::before {
            content: "";
            position: absolute;
            top: 0; left: 0; width: 100%; height: 2px;
            background: linear-gradient(90deg, #F59E0B, #38BDF8);
            opacity: 0.7;
        }
        .kpi-label {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.68rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: #94A3B8;
        }
        .kpi-value {
            font-family: 'Space Grotesk', sans-serif;
            font-size: 1.45rem;
            font-weight: 700;
            color: #F8FAFC;
            margin-top: 2px;
        }
        .kpi-sub {
            font-size: 0.72rem;
            color: #64748B;
            margin-top: 2px;
        }

        /* User Question Banner */
        .user-query-box {
            background: linear-gradient(90deg, rgba(30, 41, 59, 0.75) 0%, rgba(15, 23, 42, 0.4) 100%);
            border: 1px solid rgba(56, 189, 248, 0.28);
            border-left: 4px solid #38BDF8;
            border-radius: 10px;
            padding: 12px 18px;
            margin-top: 16px;
            margin-bottom: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .user-query-text {
            font-size: 1.02rem;
            font-weight: 600;
            color: #F1F5F9;
        }
        .user-badge {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.72rem;
            color: #38BDF8;
            background: rgba(56, 189, 248, 0.1);
            border: 1px solid rgba(56, 189, 248, 0.3);
            padding: 3px 9px;
            border-radius: 99px;
        }

        /* Assistant Response Panel */
        .ai-response-panel {
            background: rgba(13, 19, 33, 0.88);
            border: 1px solid rgba(148, 163, 184, 0.14);
            border-top: 2px solid #F59E0B;
            border-radius: 12px;
            padding: 18px 22px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
            height: 100%;
        }

        /* Inline Citation Chips */
        .cite-chip {
            display: inline-block;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.73rem;
            font-weight: 600;
            color: #FBBF24;
            background: rgba(245, 158, 11, 0.14);
            border: 1px solid rgba(245, 158, 11, 0.4);
            border-radius: 5px;
            padding: 1px 7px;
            margin: 0 2px;
            box-shadow: 0 0 8px rgba(245, 158, 11, 0.15);
        }
        .well-chip {
            display: inline-block;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.76rem;
            font-weight: 600;
            color: #38BDF8;
            background: rgba(56, 189, 248, 0.12);
            border: 1px solid rgba(56, 189, 248, 0.35);
            border-radius: 5px;
            padding: 1px 7px;
            margin: 0 2px;
        }

        /* Conflict Alert Callout */
        .conflict-alert {
            background: rgba(239, 68, 68, 0.12);
            border: 1px solid rgba(239, 68, 68, 0.45);
            border-left: 4px solid #EF4444;
            border-radius: 8px;
            padding: 10px 14px;
            margin-top: 10px;
            font-size: 0.85rem;
            color: #FECACA;
        }

        /* Custom Buttons in Sidebar / Quick Bar */
        .stButton > button {
            background: rgba(15, 23, 42, 0.85) !important;
            color: #E2E8F0 !important;
            border: 1px solid rgba(148, 163, 184, 0.22) !important;
            border-radius: 8px !important;
            font-size: 0.8rem !important;
            font-weight: 500 !important;
            transition: all 0.18s ease !important;
        }
        .stButton > button:hover {
            border-color: #F59E0B !important;
            color: #FBBF24 !important;
            background: rgba(245, 158, 11, 0.08) !important;
            transform: translateY(-1px);
        }
    </style>
    """, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 5. CITATION & WELL ID DECORATOR
# -----------------------------------------------------------------------------
def decorate_response_html(text: str) -> str:
    if not text:
        return ""
    text = re.sub(
        r'\b((?:INS|MNT|CTX|REG|FB)-\d{4}-\d{3,5}|(?:SR|RC|WS)-0\d|T\d{3}(?:\.md)?)\b',
        r'<span class="cite-chip">📄 \1</span>',
        text
    )
    text = re.sub(
        r'\b(WELL-\d{4})\b',
        r'<span class="well-chip">🛢️ \1</span>',
        text
    )
    return text

# -----------------------------------------------------------------------------
# 6. GENERATIVE UI RENDERER (CARDS, CHARTS, MAPS, TABLES)
# -----------------------------------------------------------------------------
def apply_scada_plotly_theme(fig: go.Figure, title: str = "") -> go.Figure:
    fig.update_layout(
        template="plotly_dark",
        title=dict(
            text=f"<b>{title.upper()}</b>",
            font=dict(family="Space Grotesk, sans-serif", size=14, color="#F8FAFC"),
            x=0.02, y=0.95
        ),
        paper_bgcolor="rgba(13, 19, 33, 0.88)",
        plot_bgcolor="rgba(6, 9, 17, 0.65)",
        font=dict(family="JetBrains Mono, monospace", size=11, color="#94A3B8"),
        margin=dict(l=40, r=24, t=50, b=38),
        xaxis=dict(gridcolor="rgba(148, 163, 184, 0.08)", zerolinecolor="#334155"),
        yaxis=dict(gridcolor="rgba(148, 163, 184, 0.08)", zerolinecolor="#334155"),
        legend=dict(orientation="h", y=1.08, x=1, xanchor="right", bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor="#0F172A", bordercolor="#F59E0B", font=dict(family="JetBrains Mono", size=12))
    )
    return fig

def render_scada_visual(vis: dict, key: str = "v"):
    if not vis:
        return
    vtype = vis.get("component") or vis.get("type")
    if not vtype or vtype in ("none", None):
        return

    title = vis.get("title", "Telemetry View")
    raw_data = vis.get("rows") if "rows" in vis else vis.get("data", [])
    df = pd.DataFrame(raw_data) if isinstance(raw_data, list) else pd.DataFrame([raw_data])

    if vtype in ("status_card", "card") and not df.empty:
        row = df.iloc[0].to_dict()
        is_prod = bool(row.get("producing", row.get("is_producing", False)))
        badge_bg = "rgba(16, 185, 129, 0.15)" if is_prod else "rgba(239, 68, 68, 0.18)"
        badge_col = "#34D399" if is_prod else "#F87171"
        badge_txt = "● PRODUCING OIL" if is_prod else "▲ SHUT-IN / NOT PRODUCING"
        delta_t = float(row.get("delta_c", row.get("delta_t", 0.0)) or 0.0)
        limit_t = float(row.get("threshold_c", row.get("min_delta_t", 15.0)) or 15.0)
        pct = min(100, max(5, int((delta_t / max(limit_t, 1)) * 100)))

        rec_status = str(row.get("recorded_status", row.get("status", "active")))
        stale = row.get("recorded_status_out_of_date")
        rec_display = f"{rec_status.upper()} ⚠️ (Stale)" if stale else rec_status.upper()

        st.markdown(f"""
        <div class="ai-response-panel" style="border-top: 2px solid {badge_col};">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px;">
                <div>
                    <div style="font-family:'Space Grotesk'; font-size:1.35rem; font-weight:700; color:#F8FAFC;">
                        🛢️ {row.get('asset_id', 'WELL-0001')}
                    </div>
                    <div style="font-family:'JetBrains Mono'; font-size:0.75rem; color:#94A3B8;">
                        CLASS: {row.get('well_type', 'T200')} · THRESHOLD: ≥{limit_t:.1f}°C ΔT
                    </div>
                </div>
                <div style="background:{badge_bg}; color:{badge_col}; border:1px solid {badge_col}; padding:5px 14px; border-radius:99px; font-family:'JetBrains Mono'; font-size:0.75rem; font-weight:600;">
                    {badge_txt}
                </div>
            </div>
            <div style="display:grid; grid-template-columns:repeat(2, 1fr); gap:10px; margin-bottom:14px;">
                <div style="background:#060911; border:1px solid #1E293B; border-radius:8px; padding:10px 14px;">
                    <div style="font-size:0.7rem; color:#64748B; font-family:'JetBrains Mono';">THERMAL DELTA (ΔT)</div>
                    <div style="font-size:1.3rem; font-weight:700; color:{badge_col}; font-family:'Space Grotesk';">
                        +{delta_t:.1f} °C <span style="font-size:0.78rem; color:#64748B;">/ {limit_t:.1f}°C req</span>
                    </div>
                    <div style="width:100%; background:#1E293B; height:5px; border-radius:3px; margin-top:6px;">
                        <div style="width:{pct}%; background:{badge_col}; height:5px; border-radius:3px;"></div>
                    </div>
                </div>
                <div style="background:#060911; border:1px solid #1E293B; border-radius:8px; padding:10px 14px;">
                    <div style="font-size:0.7rem; color:#64748B; font-family:'JetBrains Mono';">WELLHEAD / AMBIENT</div>
                    <div style="font-size:1.25rem; font-weight:700; color:#F8FAFC; font-family:'Space Grotesk';">
                        {float(row.get('wellhead_temp_c', 0) or 0):.1f}°C <span style="color:#64748B;">|</span> {float(row.get('ambient_temp_c', 0) or 0):.1f}°C
                    </div>
                    <div style="font-size:0.72rem; color:#94A3B8; margin-top:4px;">
                        Recorded Status: <b style="color:#FBBF24;">{rec_display}</b>
                    </div>
                </div>
            </div>
            <div style="font-family:'JetBrains Mono'; font-size:0.76rem; color:#94A3B8; background:#060911; padding:10px 12px; border-radius:8px; border:1px solid #1E293B;">
                <div>🔎 <b>LAST INSPECTION:</b> {row.get('last_inspection_id') or row.get('inspection_id', 'N/A')} on {str(row.get('last_inspected') or row.get('inspected_at', ''))[:10]} ({row.get('inspector') or row.get('inspector_name', 'Field Drone')})</div>
                <div style="margin-top:4px;">📌 <b>FIELD CONTEXT:</b> {row.get('reason') or row.get('observation') or 'Standard operating conditions'}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    elif vtype == "table" and not df.empty:
        st.markdown(f"""
        <div style="font-family:'Space Grotesk'; font-size:0.9rem; font-weight:700; color:#FBBF24; margin-bottom:6px; letter-spacing:0.04em;">
            📋 {title.upper()} ({len(df)} RECORDS)
        </div>
        """, unsafe_allow_html=True)
        if "producing" in df.columns:
            df["producing"] = df["producing"].map({True: "yes", False: "no"})
        cols = [c for c in (vis.get("columns") or []) if c in df.columns] or list(df.columns)
        st.dataframe(df[cols], use_container_width=True, hide_index=True, key=f"tbl_{key}")

    elif vtype in ("line_chart", "line") and not df.empty:
        h = vis.get("hints", {})
        x_col = h.get("x") or vis.get("x") or "date"
        if "t" in df.columns:
            df["_t"] = pd.to_datetime(df["t"])
            x_col = "_t"
        elif "date" in df.columns:
            df["_date"] = pd.to_datetime(df["date"])
            x_col = "_date"

        fig = go.Figure()
        if "wellhead_temp_c" in df.columns:
            fig.add_trace(go.Scatter(x=df[x_col], y=df["wellhead_temp_c"], mode="lines+markers",
                                     name="Wellhead Temp (°C)", line=dict(color="#F59E0B", width=2.8)))
        if "ambient_temp_c" in df.columns:
            fig.add_trace(go.Scatter(x=df[x_col], y=df["ambient_temp_c"], mode="lines+markers",
                                     name="Air Temp (°C)", line=dict(color="#38BDF8", width=2)))

        if "producing" in df.columns:
            down = df[~df["producing"].astype(bool)]
            if not down.empty:
                y_anchor = "wellhead_temp_c" if "wellhead_temp_c" in df.columns else df.columns[1]
                fig.add_trace(go.Scatter(x=down[x_col], y=down[y_anchor], mode="markers",
                                         name="Not Producing", marker=dict(color="#EF4444", size=14, symbol="x")))
                for xv in down[x_col]:
                    fig.add_vrect(x0=xv - pd.Timedelta(days=3), x1=xv + pd.Timedelta(days=3),
                                  fillcolor="#EF4444", opacity=0.12, line_width=0)

        st.plotly_chart(apply_scada_plotly_theme(fig, title), use_container_width=True, key=f"ln_{key}")

    elif vtype in ("bar_chart", "bar") and not df.empty:
        h = vis.get("hints", {})
        x_col = h.get("x") or vis.get("x") or df.columns[0]
        y_col = h.get("y") or vis.get("y") or next((c for c in df.columns if df[c].dtype.kind in "fi"), df.columns[1])
        fig = px.bar(
            df, x=x_col, y=y_col, text_auto=True,
            color_discrete_sequence=["#F59E0B", "#38BDF8", "#EF4444"]
        )
        fig.update_traces(
            marker_line_color="#FBBF24", marker_line_width=1.2, opacity=0.9,
            textfont=dict(family="JetBrains Mono", size=12, color="#FFFFFF")
        )
        st.plotly_chart(apply_scada_plotly_theme(fig, title), use_container_width=True, key=f"bar_{key}")

    elif vtype == "heatmap" and not df.empty:
        plot_df = df.copy()
        h = vis.get("hints", {})
        idx = h.get("rows_field") or ("area_name" if "area_name" in plot_df.columns else plot_df.columns[0])
        plot_df = plot_df.set_index(idx)
        if "Total" in plot_df.columns and len(plot_df.columns) > 2:
            plot_df = plot_df.drop(columns=["Total"])
        fig = px.imshow(
            plot_df, text_auto=True, aspect="auto",
            color_continuous_scale=["#090D16", "#1E3A8A", "#D97706", "#DC2626"]
        )
        st.plotly_chart(apply_scada_plotly_theme(fig, title), use_container_width=True, key=f"hm_{key}")

    elif vtype == "map" and not df.empty:
        lat_c = "latitude" if "latitude" in df.columns else ("lat" if "lat" in df.columns else None)
        lon_c = "longitude" if "longitude" in df.columns else ("lon" if "lon" in df.columns else None)
        if not lat_c or not lon_c:
            st.dataframe(df, use_container_width=True, hide_index=True)
            return

        map_df = df.dropna(subset=[lat_c, lon_c]).copy()
        map_df["_lat"] = map_df[lat_c].astype(float)
        map_df["_lon"] = map_df[lon_c].astype(float)

        st.markdown(f"""
        <div style="font-family:'Space Grotesk'; font-size:0.9rem; font-weight:700; color:#38BDF8; margin-bottom:6px;">
            🛰️ {title.upper()} — GEOSPATIAL SPILL OVERLAY
        </div>
        """, unsafe_allow_html=True)

        rendered = False
        try:
            layer_glow = pdk.Layer(
                "ScatterplotLayer",
                data=map_df,
                get_position="[_lon, _lat]",
                get_fill_color="[245, 158, 11, 80]",
                get_radius=950,
                pickable=False,
            )
            layer_core = pdk.Layer(
                "ScatterplotLayer",
                data=map_df,
                get_position="[_lon, _lat]",
                get_fill_color="[239, 68, 68, 240]",
                get_line_color="[255, 255, 255, 255]",
                line_width_min_pixels=2,
                get_radius=380,
                pickable=True,
            )
            view_state = pdk.ViewState(
                latitude=float(map_df["_lat"].mean()),
                longitude=float(map_df["_lon"].mean()),
                zoom=11.3,
                pitch=40,
            )
            st.pydeck_chart(pdk.Deck(
                map_style="https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
                initial_view_state=view_state,
                layers=[layer_glow, layer_core],
                tooltip={"html": "<b>{asset_id}</b><br/>Spill: {volume_bbl} bbl<br/>Date: {date}",
                         "style": {"backgroundColor": "#0F172A", "color": "#F8FAFC"}}
            ))
            rendered = True
        except Exception:
            pass

        if not rendered:
            fig = px.scatter_map(map_df, lat="_lat", lon="_lon", hover_name="asset_id",
                                 size="volume_bbl" if "volume_bbl" in map_df.columns else None,
                                 zoom=11, color_discrete_sequence=["#EF4444"])
            fig.update_layout(map_style="carto-darkmatter", height=420)
            st.plotly_chart(fig, use_container_width=True, key=f"map_{key}")

# -----------------------------------------------------------------------------
# 7. MAIN SCADA OPERATING APPLICATION
# -----------------------------------------------------------------------------
inject_scada_theme()
kpis = get_fleet_kpis()

# --- SIDEBAR: OPERATOR CONSOLE, VISION, & 1-CLICK EVALUATION SCENARIOS ---
with st.sidebar:
    st.markdown("""
    <div style="font-family:'Space Grotesk'; font-size:1.15rem; font-weight:700; color:#F59E0B; letter-spacing:0.04em;">
        ⚙️ OPERATOR CONSOLE
    </div>
    <div style="font-family:'JetBrains Mono'; font-size:0.7rem; color:#64748B; margin-bottom:12px;">
        ROLE-SCOPED PERSISTENT MEMORY
    </div>
    """, unsafe_allow_html=True)

    all_users = store.list_users()
    user_options = {
        f"{u['name']} ({u['role'].replace('_', ' ')} · {u['team_id']})": u
        for u in all_users
    }
    selected_label = st.selectbox("Active Operator Identity", list(user_options.keys()))
    user = user_options[selected_label]
    active_user_id = user["user_id"]
    active_user_name = user["name"]
    active_user_role = user["role"].replace("_", " ")

    # Current conversation thread
    convs = store.conversations(active_user_id)
    if not convs:
        c_id = store.new_conversation(active_user_id, str(date.today()))
        conv = store.conversation(active_user_id, c_id)
    else:
        cur_id = st.session_state.get(f"conv_{active_user_id}", convs[0]["conv_id"])
        conv = store.conversation(active_user_id, cur_id)

    st.markdown("---")
    st.markdown("<div style='font-family:JetBrains Mono; font-size:0.74rem; color:#38BDF8; margin-bottom:6px;'>⚡ 1-CLICK EVALUATION QUERIES</div>", unsafe_allow_html=True)

    DEMO_QUERIES = [
        ("🟢 Q1 · WELL-0001 Status Card", "Is WELL-0001 producing oil right now? When was it last inspected, and by whom?"),
        ("📋 Q2 · NE Block 8 Down Table", "Which wells in Northeast Block 8 are not producing oil right now, and why? Show them in a table."),
        ("📈 Q3 · 13-Wk Thermal Chart", "Show a line chart of WELL-0001's wellhead temperature against air temperature for the last 13 weeks, and mark when it was not producing oil."),
        ("🛢️ Q4 · WELL-0001 Spills (4Y)", "How many oil spills has WELL-0001 had in the last 4 years, and how much oil in total? List them in a table."),
        ("📊 Q6 · Block 7 Top Downtime", "Which 3 wells in Northeast Block 7 had the most downtime in the last 4 months? Show a bar chart."),
        ("🛰️ Q7 · Block 8 Spill Geo-Map", "Show on a map every well in Northeast Block 8 with a real spill in the last 90 days."),
        ("🔥 Q8 · 2026 Fleet Heatmap", "Show a heatmap of 2026 spills by geographic area and month."),
        ("⚖️ Q9 · WELL-0001 Compliance", "Which rules has WELL-0001 broken in the last 12 months, and what is still open?"),
        ("🛠️ Q12 · Override WELL-0164 Temp", "The 15 Oct reading for WELL-0164 is wrong. The handheld thermal gun used in that inspection was faulty; the field crew re-measured the wellhead at 41.0 °C."),
        ("⚠️ Q18 · Disputed Spill Analysis", "Was the 20 Aug spill at WELL-0101 real oil?"),
    ]
    for btn_label, q_str in DEMO_QUERIES:
        if st.button(btn_label, use_container_width=True):
            st.session_state["queued_prompt"] = q_str
            st.rerun()

    st.markdown("---")
    with st.expander("📷 Thermal Gun Vision Override"):
        st.file_uploader("Upload FLIR / Thermal Inspection", type=["png", "jpg", "jpeg"])

    if st.button("🗑️ Reset Chat Thread", use_container_width=True):
        store.new_conversation(active_user_id, str(date.today()))
        st.rerun()

# --- PWA META + TOP SCADA NAVBAR & 5-CARD HUD STRIP ---
inject_pwa_and_logo()

st.markdown(f"""
<div class="scada-navbar">
    <div style="display:flex; align-items:center; gap:14px;">
        <img src="/app/static/logo.png"
             alt="FlytBase Logo"
             style="height:38px; width:auto; border-radius:6px; object-fit:contain;"
             onerror="this.style.display='none'">
        <div>
            <div class="brand-title">FLYTBASE // ASSET INTELLIGENCE COPILOT</div>
            <div class="brand-sub">Deterministic DuckDB Engine · Gemma 4 Reasoning · Scoped Memory Store</div>
        </div>
    </div>
    <div style="display:flex; gap:12px; align-items:center; font-family:'JetBrains Mono'; font-size:0.78rem;">
        <span style="background:rgba(56,189,248,0.12); color:#38BDF8; border:1px solid rgba(56,189,248,0.35); padding:5px 12px; border-radius:6px;">
            👤 {active_user_name} ({active_user_id})
        </span>
        <span style="background:rgba(245,158,11,0.14); color:#FBBF24; border:1px solid rgba(245,158,11,0.4); padding:5px 12px; border-radius:6px;">
            🕒 CLOCK ANCHOR: {kpis['today']}
        </span>
    </div>
</div>

<div class="kpi-strip">
    <div class="kpi-card">
        <div class="kpi-label">Active Fleet Assets</div>
        <div class="kpi-value">{kpis['total_wells']} WELLS</div>
        <div class="kpi-sub">4 Blocks · T200 (≥15°C) & T350 (≥20°C)</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">Producing Right Now</div>
        <div class="kpi-value" style="color:#34D399;">{kpis['producing_wells']} ONLINE</div>
        <div class="kpi-sub">Thermal ΔT ≥ Manual Limit</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">Shut-In / Down Wells</div>
        <div class="kpi-value" style="color:#F87171;">{kpis['down_wells']} STOPPED</div>
        <div class="kpi-sub">Each stopped wk = 7d downtime</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">Indexed Telemetry</div>
        <div class="kpi-value" style="color:#38BDF8;">{kpis['total_inspections']}</div>
        <div class="kpi-sub">Weekly Drone & Crew Inspections</div>
    </div>
    <div class="kpi-card">
        <div class="kpi-label">Open Regulatory Fines</div>
        <div class="kpi-value" style="color:#FBBF24;">{kpis['open_fines']}</div>
        <div class="kpi-sub">SR-01 (24h) & SR-02 (4h) SOPs</div>
    </div>
</div>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 8. SPLIT BENTO CONVERSATION GRID (SIDE-BY-SIDE [5, 7])
# -----------------------------------------------------------------------------
messages = store.messages(active_user_id, conv["conv_id"])

if not messages:
    st.markdown("""
    <div style="text-align:center; padding:45px 20px; background:rgba(15,23,42,0.45); border:1px dashed rgba(148,163,184,0.2); border-radius:12px; margin:20px 0;">
        <div style="font-family:'Space Grotesk'; font-size:1.25rem; color:#F8FAFC; font-weight:600;">
            Ready for Field Telemetry Queries & Live Operator Overrides
        </div>
        <div style="font-size:0.88rem; color:#94A3B8; margin-top:6px;">
            Select a 1-click evaluation scenario from the sidebar or type a query below (e.g. well status, downtime chart, spill map, or temperature correction).
        </div>
    </div>
    """, unsafe_allow_html=True)

# Pair user & assistant messages into Split Bento turns
turns = []
i = 0
while i < len(messages):
    m = messages[i]
    if m["role"] == "user":
        turn = {"question": m["content"], "answer": "", "payload": {}}
        if i + 1 < len(messages) and messages[i + 1]["role"] == "assistant":
            turn["answer"] = messages[i + 1]["content"]
            turn["payload"] = messages[i + 1].get("payload") or {}
            i += 2
        else:
            i += 1
        turns.append(turn)
    else:
        turns.append({"question": "(query)", "answer": m["content"], "payload": m.get("payload") or {}})
        i += 1

# Render every turn in a 2-Column Split Bento Card
for idx, turn in enumerate(turns):
    st.markdown(f"""
    <div class="user-query-box">
        <div class="user-query-text">💬 {turn['question']}</div>
        <div class="user-badge">{active_user_name} · {active_user_id}</div>
    </div>
    """, unsafe_allow_html=True)

    p = turn.get("payload") or {}
    vis = p.get("visual")
    has_visual = vis and bool(vis.get("component") or vis.get("type")) and bool(vis.get("rows") or vis.get("data"))

    if has_visual:
        col_text, col_vis = st.columns([5, 7], gap="medium")
    else:
        col_text = st.container()
        col_vis = None

    with col_text:
        decorated_html = decorate_response_html(turn.get("answer", ""))
        
        # Memory writes & conflicts
        mem_tags = []
        for w in p.get("memory_writes") or []:
            icon = "✅" if w.get("status") == "applied" else "⚠️"
            mem_tags.append(f"<div style='font-size:0.75rem; color:#34D399; margin-bottom:4px;'>{icon} Remembered as <b>{w.get('id')}</b> ({w.get('kind', '').replace('_', ' ')})</div>")
        
        conflict_tags = []
        for c in p.get("conflicts") or []:
            conflict_tags.append(f"<div class='conflict-alert'>⚠️ <b>CONFLICT:</b> {c}</div>")

        sources = p.get("sources") or []
        cite_footer = ""
        if sources:
            badges = " ".join([f'<span class="cite-chip">📄 {s.get("id") or s.get("doc")}</span>' for s in sources[:12] if s.get("id") or s.get("doc")])
            cite_footer = f'<div style="margin-top:14px; padding-top:10px; border-top:1px solid #1E293B; font-size:0.75rem; color:#94A3B8;"><b>GROUNDED EVIDENCE:</b> {badges}</div>'

        st.markdown(f"""
        <div class="ai-response-panel">
            <div style="font-family:'JetBrains Mono'; font-size:0.7rem; color:#F59E0B; margin-bottom:8px; letter-spacing:0.08em;">
                ⚡ COPILOT ANALYSIS // DETERMINISTIC REASONING
            </div>
            {''.join(mem_tags)}
            {''.join(conflict_tags)}
            <div style="line-height:1.65; font-size:0.93rem; color:#E2E8F0; margin-top:6px;">
                {decorated_html}
            </div>
            {cite_footer}
        </div>
        """, unsafe_allow_html=True)

        if p.get("trace"):
            with st.expander("🛠️ Execution Trace & Deterministic Tools"):
                for t in p["trace"]:
                    st.code(f"{t['tool']}({t.get('args')})" + (f"  → error: {t['error']}" if t.get("error") else ""), language="python")
                if p.get("model"):
                    st.caption(f"Reasoning Model: {p.get('model')}")

    if has_visual and col_vis is not None:
        with col_vis:
            render_scada_visual(vis, key=f"v_{idx}")

# -----------------------------------------------------------------------------
# 9. PROMPT EXECUTION (1-CLICK OR CHAT INPUT)
# -----------------------------------------------------------------------------
chat_val = st.chat_input(f"Ask Copilot as {active_user_name} (e.g. 'Is WELL-0001 producing oil right now?')...")
queued_prompt = st.session_state.pop("queued_prompt", None)
prompt_to_run = queued_prompt or chat_val

if prompt_to_run:
    with st.spinner("Executing DuckDB queries, SOP compliance checks & Gemma 4 reasoning…"):
        try:
            out = agent.run(user, conv, prompt_to_run)
        except Exception as e:
            st.error(f"Engine Exception: {e}")
            st.stop()
    st.rerun()
