# ui_polish.py  –  Enterprise UI polish for the WellWise Streamlit copilot
"""
Injects custom CSS, renders styled status cards, citation badges, and Plotly
dark-mode wrapper.  Drop-in: import and call inject_industrial_css() right after
st.set_page_config().
"""
import re
import streamlit as st
import plotly.graph_objects as go


# ── CSS injection ──────────────────────────────────────────────────────────────

def inject_industrial_css():
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
        }

        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {background: transparent !important;}

        .block-container {
            padding-top: 1.5rem !important;
            padding-bottom: 4rem !important;
            max-width: 1250px !important;
        }

        [data-testid="stSidebar"] {
            background-color: #0F172A !important;
            border-right: 1px solid #1E293B !important;
        }

        /* Chat Message Containers */
        [data-testid="stChatMessage"] {
            background-color: #111827 !important;
            border: 1px solid #1F2937 !important;
            border-radius: 12px !important;
            padding: 1.1rem 1.25rem !important;
            margin-bottom: 0.85rem !important;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
        }
        [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
            background-color: #172033 !important;
            border-left: 3px solid #3B82F6 !important;
        }
        [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
            background-color: #111827 !important;
            border-left: 3px solid #F59E0B !important;
        }

        /* Citation Pill Badges */
        .citation-badge {
            display: inline-block;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.74rem;
            font-weight: 500;
            color: #FBBF24;
            background: rgba(245, 158, 11, 0.12);
            border: 1px solid rgba(245, 158, 11, 0.35);
            border-radius: 6px;
            padding: 2px 7px;
            margin: 0 3px;
            vertical-align: middle;
        }

        /* Conflict / Warning Callout Banner */
        .conflict-banner {
            background: rgba(239, 68, 68, 0.12);
            border-left: 4px solid #EF4444;
            border-radius: 8px;
            padding: 12px 16px;
            margin: 10px 0;
            color: #FCA5A5;
            font-size: 0.9rem;
        }

        /* Status Card Styling */
        .well-card {
            background: linear-gradient(145deg, #111827, #1E293B);
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 18px 22px;
            margin-top: 10px;
            margin-bottom: 10px;
        }
        .well-card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #334155;
            padding-bottom: 10px;
            margin-bottom: 14px;
        }
        .well-id-title {
            font-family: 'JetBrains Mono', monospace;
            font-size: 1.25rem;
            font-weight: 700;
            color: #F8FAFC;
        }
        .status-pill-producing {
            background: rgba(16, 185, 129, 0.15);
            color: #34D399;
            border: 1px solid rgba(16, 185, 129, 0.4);
            padding: 4px 12px;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        .status-pill-stopped {
            background: rgba(239, 68, 68, 0.15);
            color: #F87171;
            border: 1px solid rgba(239, 68, 68, 0.4);
            padding: 4px 12px;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }
        .metric-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 12px;
        }
        @media (max-width: 768px) {
            .metric-grid { grid-template-columns: repeat(2, 1fr); }
        }
        .metric-box {
            background: rgba(15, 23, 42, 0.65);
            border: 1px solid #1E293B;
            border-radius: 8px;
            padding: 10px 14px;
        }
        .metric-label {
            font-size: 0.75rem;
            color: #94A3B8;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }
        .metric-val {
            font-family: 'JetBrains Mono', monospace;
            font-size: 1.15rem;
            font-weight: 600;
            color: #F1F5F9;
            margin-top: 4px;
        }

        /* Evidence source list at bottom */
        .evidence-list {
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin-top: 8px;
        }

        /* Styled dataframe inside chat */
        [data-testid="stDataFrame"] {
            border-radius: 10px !important;
            overflow: hidden;
        }
    </style>
    """, unsafe_allow_html=True)


# ── Header Bar ─────────────────────────────────────────────────────────────────

def render_top_header(active_user_name: str, active_user_role: str,
                      today_date: str):
    """Renders an executive SCADA-style header bar."""
    st.markdown(f"""
    <div style="display:flex; justify-content:space-between; align-items:center;
                background:#111827; border:1px solid #1E293B; border-radius:12px;
                padding:14px 22px; margin-bottom:20px;">
        <div style="display:flex; align-items:center; gap:14px;">
            <div style="background:#F59E0B; width:12px; height:36px;
                        border-radius:4px;"></div>
            <div>
                <div style="font-size:1.25rem; font-weight:700; color:#F9FAFB;
                            letter-spacing:-0.01em;">
                    WELLWISE // ASSET INTELLIGENCE COPILOT
                </div>
                <div style="font-size:0.8rem; color:#94A3B8;">
                    Deterministic Field Telemetry · SOP Compliance ·
                    Shared Operator Memory
                </div>
            </div>
        </div>
        <div style="display:flex; gap:18px; align-items:center;
                    font-family:'JetBrains Mono', monospace; font-size:0.82rem;">
            <div style="background:#1E293B; padding:6px 12px; border-radius:6px;
                        color:#E2E8F0; border:1px solid #334155;">
                👤 {active_user_name}
                <span style="color:#94A3B8;">({active_user_role})</span>
            </div>
            <div style="background:rgba(245,158,11,0.12); padding:6px 12px;
                        border-radius:6px; color:#FBBF24;
                        border:1px solid rgba(245,158,11,0.3);">
                📅 REF DATE: {today_date}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ── Citation Formatting ────────────────────────────────────────────────────────

def format_citations_in_text(text: str) -> str:
    """Wraps IDs like INS-0001-0203, MNT-0001-021, CTX-0001-003, etc.
    in styled citation pill badges."""
    pattern = (r'\b((?:INS|MNT|CTX|REG|FB)-\d{4}-\d{3,5}'
               r'|(?:SR|RC|WS)-0\d'
               r'|T\d{3}(?:\.md)?(?:\s*(?:manual|Manual))?(?:\s*§[\d.]+)?'
               r'|WELL-\d{4})\b')
    return re.sub(pattern, r'<span class="citation-badge">\1</span>', text)


# ── Plotly Dark Wrapper ────────────────────────────────────────────────────────

def style_plotly_figure(fig: go.Figure, title: str = "") -> go.Figure:
    """Applies a unified transparent industrial dark theme to Plotly charts."""
    fig.update_layout(
        template="plotly_dark",
        title=dict(text=title,
                   font=dict(size=15, family="Inter, sans-serif",
                             color="#F8FAFC"),
                   x=0.01),
        paper_bgcolor="rgba(17, 24, 39, 0.0)",
        plot_bgcolor="rgba(15, 23, 42, 0.55)",
        font=dict(family="Inter, sans-serif", color="#CBD5E1", size=12),
        margin=dict(l=40, r=25, t=48, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="right", x=1, bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(gridcolor="#1E293B", zerolinecolor="#334155"),
        yaxis=dict(gridcolor="#1E293B", zerolinecolor="#334155"),
        hovermode="x unified",
    )
    return fig


# ── Custom Status Card ────────────────────────────────────────────────────────

def render_well_status_card(card_data: dict):
    """Renders a custom HTML status card for single-well queries."""
    is_prod = card_data.get("producing", card_data.get("is_producing", False))
    pill_cls = "status-pill-producing" if is_prod else "status-pill-stopped"
    pill_txt = ("● PRODUCING OIL" if is_prod
                else "▲ NOT PRODUCING (SHUT-IN / DOWN)")

    rec_status = str(card_data.get("recorded_status",
                                    card_data.get("status", "unknown")))
    if (not is_prod and rec_status.lower() == "active") or \
       (is_prod and rec_status.lower() == "down"):
        rec_display = f"{rec_status.upper()} ⚠️ (Stale)"
    else:
        rec_display = rec_status.upper()

    aid = card_data.get("asset_id", "WELL")
    wt = card_data.get("well_type", "")
    delta = card_data.get("delta_c", card_data.get("delta_t", 0)) or 0
    thresh = card_data.get("threshold_c", card_data.get("min_delta_t", "")) or ""
    wh = card_data.get("wellhead_temp_c", 0) or 0
    amb = card_data.get("ambient_temp_c", 0) or 0
    iid = card_data.get("inspection_id") or card_data.get("last_inspection_id") or "N/A"
    idate = str(card_data.get("inspected_at") or card_data.get("last_inspected") or card_data.get("date", ""))[:10]
    inspector = card_data.get("inspector_name") or card_data.get("inspector") or "N/A"
    reason = card_data.get("reason") or card_data.get("observation") or card_data.get("notes") or "None recorded"

    st.markdown(f"""
    <div class="well-card">
        <div class="well-card-header">
            <div>
                <span class="well-id-title">{aid}</span>
                <span style="margin-left:10px; font-size:0.82rem; color:#94A3B8;
                      background:#0F172A; padding:3px 8px; border-radius:4px;
                      border:1px solid #334155;">
                    Type: {wt} {"(Limit: ≥" + str(thresh) + "°C)" if thresh else ""}
                </span>
            </div>
            <div class="{pill_cls}">{pill_txt}</div>
        </div>
        <div class="metric-grid">
            <div class="metric-box">
                <div class="metric-label">Temp Above Air (ΔT)</div>
                <div class="metric-val"
                     style="color:{'#34D399' if is_prod else '#F87171'};">
                    +{float(delta):.1f} °C
                </div>
            </div>
            <div class="metric-box">
                <div class="metric-label">Wellhead / Ambient</div>
                <div class="metric-val">
                    {float(wh):.1f}°C / {float(amb):.1f}°C
                </div>
            </div>
            <div class="metric-box">
                <div class="metric-label">Latest Inspection</div>
                <div class="metric-val" style="font-size:0.95rem;">
                    {iid} ({idate})
                </div>
            </div>
            <div class="metric-box">
                <div class="metric-label">System Record Status</div>
                <div class="metric-val" style="font-size:0.95rem;">
                    {rec_display}
                </div>
            </div>
        </div>
        <div style="margin-top:12px; font-size:0.85rem; color:#CBD5E1;
                    border-top:1px solid #1E293B; padding-top:10px;">
            <strong>Inspector:</strong> {inspector} &nbsp;|&nbsp;
            <strong>Context / Reason:</strong> {reason or "None recorded"}
        </div>
    </div>
    """, unsafe_allow_html=True)


# ── Evidence Source Badges ─────────────────────────────────────────────────────

def render_evidence_badges(sources: list[dict]):
    """Renders source citations as pill badges under the answer."""
    if not sources:
        return
    badges = []
    for s in sources[:25]:
        label = s.get("id") or s.get("doc") or ""
        if not label:
            continue
        badges.append(f'<span class="citation-badge">{label}</span>')
    if badges:
        st.markdown(
            '<div class="evidence-list">' + " ".join(badges) + '</div>',
            unsafe_allow_html=True)


# ── Conflict Banner ───────────────────────────────────────────────────────────

def render_conflict_banner(conflicts: list[str]):
    """Renders a styled conflict/warning banner."""
    if not conflicts:
        return
    items = "".join(f"<div>⚠️ {c}</div>" for c in conflicts)
    st.markdown(f'<div class="conflict-banner">{items}</div>',
                unsafe_allow_html=True)
