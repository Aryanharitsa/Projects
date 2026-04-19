"""Dark-mode theme and small UI components for WaySafe."""
from __future__ import annotations

import streamlit as st

PRIMARY = "#FF6A3D"
BG      = "#0E1117"
CARD    = "#161A23"
MUTED   = "#8892A6"

_BAND_COLORS = {
    "Safe":      "#53E3A6",
    "Caution":   "#F9C440",
    "High Risk": "#FF7F50",
    "Danger":    "#FF3D60",
}


def band_color(band: str) -> str:
    return _BAND_COLORS.get(band, MUTED)


def inject_theme() -> None:
    st.markdown(
        f"""
        <style>
        html, body, [class*="css"] {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        }}
        .block-container {{ padding-top: 1.2rem; max-width: 1400px; }}
        [data-testid="stSidebar"] {{
            background: linear-gradient(180deg, #0E1117 0%, #141926 100%);
            border-right: 1px solid rgba(255,255,255,0.05);
        }}
        h1, h2, h3 {{ letter-spacing: -0.02em; font-weight: 700; }}
        .ws-brand {{ display:flex; align-items:center; gap:.7rem; margin-bottom:.3rem; }}
        .ws-brand-logo {{
            width: 42px; height: 42px; border-radius: 12px;
            background: conic-gradient(from 120deg, #FF6A3D, #F9C440, #53E3A6, #3DA9FC, #FF6A3D);
            box-shadow: 0 4px 16px rgba(255,106,61,0.25);
        }}
        .ws-brand-title {{ font-size: 1.35rem; font-weight: 800; letter-spacing: -0.02em; }}
        .ws-brand-sub   {{ font-size: .8rem; color: {MUTED}; }}
        .ws-card {{
            background: {CARD};
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 14px;
            padding: 16px 18px;
            margin-bottom: 12px;
        }}
        .ws-ring {{
            width: 128px; height: 128px; border-radius: 50%;
            display:flex; align-items:center; justify-content:center;
            position: relative;
            background: conic-gradient(var(--ring) calc(var(--pct) * 1%), rgba(255,255,255,0.07) 0);
            flex-shrink: 0;
        }}
        .ws-ring::after {{
            content:""; position:absolute; inset:10px;
            background: {CARD}; border-radius: 50%;
        }}
        .ws-ring-inner {{
            position: relative; z-index: 1; text-align:center;
        }}
        .ws-ring-val  {{ font-size: 2.1rem; font-weight: 800; line-height: 1; }}
        .ws-ring-band {{
            font-size: .7rem; letter-spacing: .1em; text-transform: uppercase;
            margin-top: 4px; font-weight: 700;
        }}
        .ws-pill {{
            display:inline-block; padding: 3px 10px; border-radius: 999px;
            font-size: .72rem; font-weight: 600; letter-spacing: .02em;
            background: rgba(255,106,61,0.12); color: {PRIMARY};
            border: 1px solid rgba(255,106,61,0.28);
            margin: 2px 4px 2px 0;
        }}
        .ws-pill.pos {{
            background: rgba(83,227,166,0.12); color:#53E3A6;
            border-color: rgba(83,227,166,0.28);
        }}
        .ws-kicker {{
            font-size: .75rem; color: {MUTED};
            letter-spacing: .1em; text-transform: uppercase; font-weight: 600;
        }}
        .stButton>button {{ border-radius: 10px; font-weight: 600; }}
        .stButton>button[kind="primary"] {{
            background: linear-gradient(135deg, #FF6A3D 0%, #F9C440 100%);
            color: #0E1117; border: none;
        }}
        .stButton>button[kind="primary"]:hover {{ filter: brightness(1.08); }}
        div[data-testid="stMetricValue"] {{ font-weight: 700; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_brand(subtitle: str = "Smart Tourism · Safety Intelligence") -> None:
    st.markdown(
        f"""
        <div class="ws-brand">
          <div class="ws-brand-logo"></div>
          <div>
            <div class="ws-brand-title">WaySafe</div>
            <div class="ws-brand-sub">{subtitle}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_score_card(result) -> None:
    """Render the live safety score ring + top factors. `result` is a SafetyResult."""
    ring = band_color(result.band)
    pills = "".join(
        f'<span class="ws-pill{" pos" if f["impact"] > 0 else ""}">'
        f'{f["label"]} ({"+" if f["impact"] > 0 else ""}{f["impact"]})</span>'
        for f in result.factors[:5]
    ) or '<span class="ws-pill pos">Baseline · no risk factors detected</span>'

    help_line = (
        f"· nearest help {result.nearest_help_km} km"
        if result.nearest_help_km is not None else ""
    )

    st.markdown(
        f"""
        <div class="ws-card" style="display:flex; gap:20px; align-items:center;">
          <div class="ws-ring" style="--pct:{result.score}; --ring:{ring};">
            <div class="ws-ring-inner">
              <div class="ws-ring-val" style="color:{ring}">{result.score}</div>
              <div class="ws-ring-band" style="color:{ring}">{result.band}</div>
            </div>
          </div>
          <div style="flex:1; min-width:0;">
            <div class="ws-kicker">Live safety score</div>
            <div style="font-size:1.05rem; font-weight:600; margin:4px 0 10px;">
              {result.incidents_nearby} nearby incident(s) {help_line}
            </div>
            <div>{pills}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
