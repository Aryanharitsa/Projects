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
        .ws-route-grid {{
            display:grid; grid-template-columns: 1fr 1fr; gap: 14px;
        }}
        .ws-route-card {{
            background: {CARD};
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 14px;
            padding: 16px 18px;
            position: relative; overflow: hidden;
        }}
        .ws-route-card::before {{
            content:""; position:absolute; inset:0 0 auto 0; height: 3px;
            background: var(--accent, {PRIMARY});
            box-shadow: 0 0 18px var(--accent, {PRIMARY});
        }}
        .ws-route-mode {{
            display:flex; align-items:center; justify-content:space-between;
            margin-bottom: 10px;
        }}
        .ws-route-mode-name {{
            font-size: .72rem; letter-spacing: .14em; text-transform: uppercase;
            color: var(--accent, {PRIMARY}); font-weight: 800;
        }}
        .ws-route-mode-tag {{
            font-size: .65rem; letter-spacing: .08em; text-transform: uppercase;
            padding: 3px 9px; border-radius: 999px;
            background: rgba(255,255,255,0.05); color: {MUTED}; font-weight: 700;
        }}
        .ws-route-stats {{
            display:grid; grid-template-columns: repeat(4, minmax(0,1fr));
            gap: 10px; margin: 8px 0 10px;
        }}
        .ws-route-stat {{ background: rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.05); border-radius: 10px; padding: 8px 10px; }}
        .ws-route-stat-label {{ font-size:.62rem; letter-spacing:.12em; text-transform:uppercase; color:{MUTED}; font-weight:600; }}
        .ws-route-stat-val {{ font-size:1.25rem; font-weight:800; line-height: 1.05; margin-top: 2px; }}
        .ws-route-stat-sub {{ font-size:.7rem; color:{MUTED}; margin-top: 2px; }}
        .ws-route-bar-track {{ background: rgba(255,255,255,0.06); height: 6px; border-radius: 999px; overflow: hidden; margin: 6px 0 4px; }}
        .ws-route-bar-fill  {{ height: 100%; border-radius: 999px; background: var(--accent, {PRIMARY}); transition: width .8s ease; }}
        .ws-route-notes li {{ font-size: .82rem; color: #D4DAEA; margin: 2px 0; }}
        .ws-route-mini-ring {{
            width: 56px; height: 56px; border-radius: 50%;
            background: conic-gradient(var(--accent) calc(var(--pct) * 1%), rgba(255,255,255,0.07) 0);
            display:flex; align-items:center; justify-content:center; position: relative;
        }}
        .ws-route-mini-ring::after {{ content:""; position:absolute; inset:6px; background:{CARD}; border-radius:50%; }}
        .ws-route-mini-ring span {{ position:relative; z-index:1; font-weight:800; font-size:1.05rem; color: var(--accent); }}
        .ws-route-head {{ display:flex; gap:14px; align-items:center; }}
        .ws-route-headline {{ flex:1; }}
        .ws-route-headline-big {{ font-size:1.4rem; font-weight:800; }}
        .ws-route-headline-sub {{ font-size:.75rem; color:{MUTED}; }}
        .ws-summary {{
            background: linear-gradient(135deg, rgba(61,169,252,0.10) 0%, rgba(83,227,166,0.08) 100%);
            border: 1px solid rgba(61,169,252,0.22);
            border-radius: 14px; padding: 14px 18px; margin-bottom: 12px;
            display:flex; gap:24px; flex-wrap:wrap;
        }}
        .ws-summary-item {{ flex: 1; min-width: 150px; }}
        .ws-summary-item-label {{ font-size:.65rem; letter-spacing:.14em; text-transform:uppercase; color:{MUTED}; font-weight:700; }}
        .ws-summary-item-val   {{ font-size:1.3rem; font-weight:800; margin-top: 2px; }}
        @media (max-width: 900px) {{
            .ws-route-grid {{ grid-template-columns: 1fr; }}
            .ws-route-stats {{ grid-template-columns: repeat(2, 1fr); }}
        }}
        .ws-fc-card {{
            background: linear-gradient(135deg, rgba(167,139,250,0.10) 0%, rgba(94,234,212,0.06) 100%);
            border: 1px solid rgba(167,139,250,0.28);
            border-radius: 14px; padding: 16px 18px; margin-bottom: 12px;
            display:flex; gap:18px; align-items:center;
        }}
        .ws-fc-ring {{
            width:104px; height:104px; border-radius:50%; flex-shrink:0;
            background: conic-gradient(var(--ring) calc(var(--pct) * 1%), rgba(255,255,255,0.07) 0);
            display:flex; align-items:center; justify-content:center; position: relative;
        }}
        .ws-fc-ring::after {{ content:""; position:absolute; inset:8px; background:#181b29; border-radius:50%; }}
        .ws-fc-ring-inner {{ position:relative; z-index:1; text-align:center; }}
        .ws-fc-ring-val   {{ font-size:1.8rem; font-weight:800; line-height:1; color: var(--ring); }}
        .ws-fc-ring-band  {{ font-size:.62rem; letter-spacing:.14em; text-transform:uppercase; color:{MUTED}; margin-top:3px; font-weight:700; }}
        .ws-fc-meta-label {{ font-size:.62rem; letter-spacing:.14em; text-transform:uppercase; color:{MUTED}; font-weight:700; }}
        .ws-fc-meta-val   {{ font-size:1.05rem; font-weight:700; }}
        .ws-fc-pill {{
            display:inline-block; padding:3px 10px; border-radius:999px;
            font-size:.7rem; font-weight:700; letter-spacing:.04em; margin-right:6px;
        }}
        .ws-fc-pill.high   {{ background:rgba(255,61,96,0.16);  color:#FF6680; border:1px solid rgba(255,61,96,0.36); }}
        .ws-fc-pill.medium {{ background:rgba(249,196,64,0.16); color:#F9D87A; border:1px solid rgba(249,196,64,0.36); }}
        .ws-fc-pill.low    {{ background:rgba(83,227,166,0.14); color:#7BE7C2; border:1px solid rgba(83,227,166,0.34); }}
        .ws-fc-pill.cat    {{ background:rgba(167,139,250,0.14); color:#C8B8FF; border:1px solid rgba(167,139,250,0.34); }}
        .ws-fc-bars {{ display:flex; align-items:flex-end; gap:3px; height:74px; padding:6px 4px; background: rgba(255,255,255,0.03); border-radius:10px; border:1px solid rgba(255,255,255,0.05); }}
        .ws-fc-bar {{ flex:1; min-width:6px; background: var(--bar, {FORECAST_PRIMARY}); border-radius:3px 3px 0 0; transition: height .4s ease, background .4s ease; opacity:.92; }}
        .ws-fc-bar.peak {{ box-shadow: 0 0 12px var(--bar); opacity:1; }}
        .ws-fc-axis {{ display:flex; justify-content:space-between; font-size:.6rem; color:{MUTED}; margin-top:4px; letter-spacing:.06em; }}
        .ws-fc-cat {{ display:flex; align-items:center; gap:8px; margin: 4px 0; }}
        .ws-fc-cat-name {{ width:80px; font-size:.78rem; color:#D4DAEA; font-weight:600; text-transform:capitalize; }}
        .ws-fc-cat-bar  {{ flex:1; height:6px; background: rgba(255,255,255,0.06); border-radius:999px; overflow:hidden; }}
        .ws-fc-cat-fill {{ height:100%; background: linear-gradient(90deg, {FORECAST_PRIMARY}, {FORECAST_SECONDARY}); border-radius:999px; }}
        .ws-fc-cat-pct  {{ width:38px; text-align:right; font-size:.72rem; color:{MUTED}; font-variant-numeric: tabular-nums; }}
        .ws-fc-window {{
            background: linear-gradient(135deg, rgba(94,234,212,0.10) 0%, rgba(167,139,250,0.10) 100%);
            border: 1px solid rgba(94,234,212,0.30);
            border-radius: 14px; padding: 14px 18px; margin-bottom: 12px;
        }}
        .ws-fc-window-row {{ display:flex; align-items:center; justify-content:space-between; gap:12px; padding: 6px 0; border-bottom: 1px solid rgba(255,255,255,0.05); }}
        .ws-fc-window-row:last-child {{ border-bottom: none; }}
        .ws-fc-window-time {{ font-size:1.0rem; font-weight:800; color:#5EEAD4; }}
        .ws-fc-window-meta {{ font-size:.78rem; color:{MUTED}; }}
        .ws-fc-window-tag  {{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:.62rem; font-weight:700; letter-spacing:.06em; }}
        .ws-fc-window-tag.best {{ background:rgba(83,227,166,0.18); color:#7BE7C2; }}
        .ws-fc-window-tag.your {{ background:rgba(249,196,64,0.18); color:#F9D87A; }}
        .ws-hotspot-row {{
            display:grid; grid-template-columns: 56px 1fr auto; gap:14px; align-items:center;
            background: rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.05);
            border-radius:12px; padding: 10px 14px; margin-bottom: 8px;
        }}
        .ws-hotspot-rank {{
            display:flex; align-items:center; justify-content:center; width:40px; height:40px;
            border-radius: 12px; font-weight:800; color:#0E1117;
            background: linear-gradient(135deg, {FORECAST_PRIMARY}, {FORECAST_SECONDARY});
        }}
        .ws-hotspot-coord {{ font-size:.8rem; color:#D4DAEA; font-variant-numeric: tabular-nums; }}
        .ws-hotspot-meta  {{ font-size:.7rem; color:{MUTED}; }}
        .ws-hotspot-risk  {{ font-size:1.2rem; font-weight:800; }}

        /* ------------- Live Trip Companion ------------- */
        .ws-live-head {{
            display: grid;
            grid-template-columns: 144px 1fr;
            gap: 18px; align-items: center;
            background: linear-gradient(135deg, rgba(94,234,212,0.10) 0%, rgba(167,139,250,0.10) 100%);
            border: 1px solid rgba(94,234,212,0.28);
            border-radius: 16px; padding: 16px 18px; margin-bottom: 14px;
            position: relative; overflow: hidden;
        }}
        .ws-live-head::before {{
            content: ""; position: absolute; inset: 0;
            background: radial-gradient(circle at 90% 0%, rgba(94,234,212,0.18) 0%, transparent 55%);
            pointer-events: none;
        }}
        .ws-live-progress {{
            width: 124px; height: 124px; border-radius: 50%; flex-shrink: 0;
            background: conic-gradient(var(--accent, #5EEAD4) calc(var(--pct,0) * 1%), rgba(255,255,255,0.07) 0);
            display: flex; align-items: center; justify-content: center;
            position: relative;
            box-shadow: 0 0 28px rgba(94,234,212,0.18) inset;
        }}
        .ws-live-progress::after {{
            content: ""; position: absolute; inset: 9px;
            background: #131726; border-radius: 50%;
        }}
        .ws-live-progress-inner {{ position: relative; z-index: 1; text-align: center; }}
        .ws-live-progress-pct  {{ font-size: 2.0rem; font-weight: 800; line-height: 1; color: var(--accent, #5EEAD4); }}
        .ws-live-progress-cap  {{ font-size: .62rem; letter-spacing: .14em; text-transform: uppercase; color: {MUTED}; margin-top: 4px; font-weight: 700; }}
        .ws-live-meta {{ display: grid; gap: 4px; }}
        .ws-live-route {{
            font-size: .68rem; letter-spacing: .12em; text-transform: uppercase;
            color: {MUTED}; font-weight: 700;
        }}
        .ws-live-title {{ font-size: 1.32rem; font-weight: 800; letter-spacing: -0.01em; }}
        .ws-live-stats {{
            display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 10px; margin-top: 10px;
        }}
        .ws-live-stat {{
            background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06);
            border-radius: 10px; padding: 8px 10px;
        }}
        .ws-live-stat-label {{ font-size:.6rem; letter-spacing:.13em; text-transform:uppercase; color:{MUTED}; font-weight:700; }}
        .ws-live-stat-val   {{ font-size:1.18rem; font-weight:800; line-height:1.05; margin-top:2px; }}
        .ws-live-status-pulse {{
            display: inline-flex; align-items: center; gap: 6px;
            padding: 3px 10px; border-radius: 999px; font-size: .68rem;
            font-weight: 700; letter-spacing: .08em; text-transform: uppercase;
            background: rgba(94,234,212,0.14); color: #5EEAD4;
            border: 1px solid rgba(94,234,212,0.34);
        }}
        .ws-live-status-pulse .ws-dot {{
            width: 8px; height: 8px; border-radius: 50%;
            background: #5EEAD4; box-shadow: 0 0 0 0 rgba(94,234,212,0.7);
            animation: ws-pulse 1.6s infinite;
        }}
        .ws-live-status-pulse.paused {{ background: rgba(255,255,255,0.06); color: {MUTED}; border-color: rgba(255,255,255,0.12); }}
        .ws-live-status-pulse.paused .ws-dot {{ background: {MUTED}; animation: none; }}
        .ws-live-status-pulse.completed {{ background: rgba(83,227,166,0.14); color:#7BE7C2; border-color: rgba(83,227,166,0.36); }}
        .ws-live-status-pulse.completed .ws-dot {{ background: #7BE7C2; animation: none; }}
        .ws-live-status-pulse.cancelled {{ background: rgba(255,127,80,0.14); color:#FFA17A; border-color: rgba(255,127,80,0.36); }}
        .ws-live-status-pulse.cancelled .ws-dot {{ background: #FFA17A; animation: none; }}
        @keyframes ws-pulse {{
            0%   {{ box-shadow: 0 0 0 0 rgba(94,234,212,0.7); }}
            70%  {{ box-shadow: 0 0 0 10px rgba(94,234,212,0); }}
            100% {{ box-shadow: 0 0 0 0 rgba(94,234,212,0); }}
        }}
        .ws-live-bar-track {{ background: rgba(255,255,255,0.07); height: 8px; border-radius: 999px; overflow: hidden; margin-top: 10px; }}
        .ws-live-bar-fill  {{
            height: 100%; border-radius: 999px;
            background: linear-gradient(90deg, #5EEAD4 0%, #A78BFA 100%);
            transition: width .8s ease;
        }}
        .ws-alert-feed {{ display: flex; flex-direction: column; gap: 8px; }}
        .ws-alert {{
            display: grid; grid-template-columns: 28px 1fr auto; gap: 10px; align-items: center;
            background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06);
            border-left: 3px solid var(--tone, {MUTED});
            border-radius: 10px; padding: 8px 12px;
        }}
        .ws-alert-icon {{ font-size: 1.05rem; text-align: center; }}
        .ws-alert-msg  {{ font-size: .82rem; color:#D9DEEC; line-height: 1.35; }}
        .ws-alert-time {{ font-size: .68rem; color:{MUTED}; font-variant-numeric: tabular-nums; white-space: nowrap; }}
        .ws-alert.info     {{ --tone: #5EEAD4; }}
        .ws-alert.warn     {{ --tone: #F9C440; background: rgba(249,196,64,0.04); }}
        .ws-alert.critical {{
            --tone: #FF3D60; background: rgba(255,61,96,0.05);
            box-shadow: 0 0 18px rgba(255,61,96,0.10) inset;
        }}
        .ws-look-card {{
            background: {CARD}; border: 1px solid rgba(255,255,255,0.06);
            border-radius: 14px; padding: 14px 16px; margin-bottom: 12px;
        }}
        .ws-look-row {{
            display: grid; grid-template-columns: 56px 1fr 70px;
            gap: 10px; align-items: center; padding: 6px 0;
            border-bottom: 1px dashed rgba(255,255,255,0.06);
        }}
        .ws-look-row:last-child {{ border-bottom: none; }}
        .ws-look-d   {{ font-size: .82rem; font-weight:700; color:#D4DAEA; font-variant-numeric: tabular-nums; }}
        .ws-look-bar {{ height: 8px; background: rgba(255,255,255,0.06); border-radius: 999px; overflow: hidden; }}
        .ws-look-fill {{ height: 100%; border-radius: 999px; background: var(--tone, #5EEAD4); transition: width .4s ease; }}
        .ws-look-pct {{ text-align: right; font-size: .78rem; font-weight: 700; color: var(--tone, #5EEAD4); font-variant-numeric: tabular-nums; }}
        .ws-contact {{
            display: inline-flex; align-items: center; gap: 8px;
            padding: 5px 12px 5px 5px; border-radius: 999px;
            background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.07);
            margin: 0 6px 6px 0;
        }}
        .ws-contact-avatar {{
            width: 26px; height: 26px; border-radius: 50%;
            display: flex; align-items: center; justify-content: center;
            font-size: .68rem; font-weight: 800; color: #0E1117;
            background: linear-gradient(135deg, var(--c1, #5EEAD4), var(--c2, #A78BFA));
        }}
        .ws-contact-name {{ font-size: .8rem; font-weight: 700; color:#D4DAEA; }}
        .ws-contact-rel  {{ font-size: .65rem; color:{MUTED}; }}
        .ws-broadcast-row {{
            display: grid; grid-template-columns: 30px 1fr auto; gap: 8px; align-items: start;
            padding: 7px 0; border-bottom: 1px dashed rgba(255,255,255,0.06);
        }}
        .ws-broadcast-row:last-child {{ border-bottom: none; }}
        .ws-broadcast-name {{ font-size:.78rem; font-weight:700; color:#D4DAEA; }}
        .ws-broadcast-body {{ font-size:.74rem; color:{MUTED}; line-height:1.35; }}
        .ws-broadcast-time {{ font-size:.66rem; color:{MUTED}; font-variant-numeric: tabular-nums; white-space: nowrap; }}
        .ws-broadcast-kind {{
            font-size:.58rem; font-weight:800; letter-spacing:.1em; text-transform:uppercase;
            padding: 2px 7px; border-radius: 999px; display:inline-block; margin-bottom: 2px;
            background: rgba(167,139,250,0.16); color:#C8B8FF;
        }}
        .ws-broadcast-kind.auto_sos {{ background: rgba(255,61,96,0.18); color:#FF6680; }}
        .ws-broadcast-kind.departure {{ background: rgba(94,234,212,0.16); color:#7EE7DA; }}
        .ws-broadcast-kind.arrival {{ background: rgba(83,227,166,0.16); color:#7BE7C2; }}
        .ws-trip-empty {{
            background: {CARD}; border: 1px dashed rgba(255,255,255,0.12);
            border-radius: 14px; padding: 36px 24px; text-align: center;
        }}
        .ws-trip-empty-icon {{ font-size: 2.6rem; margin-bottom: 8px; }}
        .ws-trip-empty h4 {{ margin: 0 0 6px; font-weight:800; letter-spacing:-0.01em; }}
        .ws-trip-empty p  {{ color: {MUTED}; font-size: .85rem; margin: 0; }}
        .ws-mini-pill {{
            display: inline-block; padding: 2px 8px; border-radius: 999px;
            font-size: .64rem; font-weight: 800; letter-spacing: .08em;
            background: rgba(255,255,255,0.05); color:{MUTED}; border:1px solid rgba(255,255,255,0.08);
            margin-right: 4px;
        }}
        .ws-trip-log-row {{
            display: grid; grid-template-columns: 1fr auto; gap: 14px; align-items: center;
            padding: 10px 14px; border-radius: 12px; margin-bottom: 8px;
            background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.06);
        }}
        .ws-trip-log-title {{ font-size: .9rem; font-weight: 700; color: #D4DAEA; }}
        .ws-trip-log-meta  {{ font-size: .7rem; color:{MUTED}; }}
        .ws-trip-log-stats {{ display:flex; gap: 6px; flex-wrap: wrap; }}
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


ROUTE_ACCENT = {
    "fastest":          "#F9C440",
    "safest":           "#3DA9FC",
    "forecast-safest":  "#A78BFA",   # purple — "predicted-safest"
}

FORECAST_RAMP = ("#53E3A6", "#F9C440", "#FF6A3D", "#FF3D60")  # safe → danger
FORECAST_PRIMARY = "#A78BFA"
FORECAST_SECONDARY = "#5EEAD4"


def forecast_color(risk: float) -> str:
    """0..1 → ramp colour."""
    r = max(0.0, min(1.0, risk))
    if r < 0.25:  return FORECAST_RAMP[0]
    if r < 0.50:  return FORECAST_RAMP[1]
    if r < 0.75:  return FORECAST_RAMP[2]
    return FORECAST_RAMP[3]


def _route_card_html(route, accent: str) -> str:
    pct = max(0, min(100, route.avg_safety))
    notes = "".join(f"<li>{n}</li>" for n in route.notes)
    mode_label = "Safest path" if route.mode == "safest" else "Fastest path"
    sub = "Risk-aware A* over geofences + recent incidents" if route.mode == "safest" \
          else "Shortest distance, ignores risk"
    return f"""
    <div class="ws-route-card" style="--accent:{accent};">
      <div class="ws-route-mode">
        <span class="ws-route-mode-name">{mode_label}</span>
        <span class="ws-route-mode-tag">{route.mode.upper()}</span>
      </div>
      <div class="ws-route-head">
        <div class="ws-route-mini-ring" style="--pct:{pct}; --accent:{accent};">
          <span>{route.avg_safety}</span>
        </div>
        <div class="ws-route-headline">
          <div class="ws-route-headline-big">{route.distance_km:g} km · {route.eta_minutes:g} min</div>
          <div class="ws-route-headline-sub">{sub}</div>
          <div class="ws-route-bar-track"><div class="ws-route-bar-fill" style="width:{pct}%;"></div></div>
        </div>
      </div>
      <div class="ws-route-stats">
        <div class="ws-route-stat">
          <div class="ws-route-stat-label">Distance</div>
          <div class="ws-route-stat-val">{route.distance_km:g} <span style="font-size:.7rem;color:#8892A6">km</span></div>
        </div>
        <div class="ws-route-stat">
          <div class="ws-route-stat-label">ETA</div>
          <div class="ws-route-stat-val">{route.eta_minutes:g} <span style="font-size:.7rem;color:#8892A6">min</span></div>
        </div>
        <div class="ws-route-stat">
          <div class="ws-route-stat-label">Min safety</div>
          <div class="ws-route-stat-val">{route.min_safety}</div>
          <div class="ws-route-stat-sub">at riskiest point</div>
        </div>
        <div class="ws-route-stat">
          <div class="ws-route-stat-label">Risk km</div>
          <div class="ws-route-stat-val">{route.max_risk_segment_km:g}</div>
          <div class="ws-route-stat-sub">elevated-risk km</div>
        </div>
      </div>
      <ul class="ws-route-notes" style="padding-left:18px; margin:0;">{notes}</ul>
    </div>
    """


def render_route_compare(safest, fastest) -> None:
    safe_html = _route_card_html(safest, ROUTE_ACCENT["safest"])
    fast_html = _route_card_html(fastest, ROUTE_ACCENT["fastest"])
    st.markdown(
        f'<div class="ws-route-grid">{safe_html}{fast_html}</div>',
        unsafe_allow_html=True,
    )


def render_route_summary(safest, fastest) -> None:
    detour_pct = ((safest.distance_km / max(0.01, fastest.distance_km)) - 1.0) * 100
    safety_gain = safest.avg_safety - fastest.avg_safety
    eta_delta = safest.eta_minutes - fastest.eta_minutes
    risk_avoided = max(0.0, fastest.max_risk_segment_km - safest.max_risk_segment_km)
    detour_str = f"+{detour_pct:.1f}%" if detour_pct > 0 else f"{detour_pct:.1f}%"
    eta_str = f"+{eta_delta:.0f} min" if eta_delta > 0 else f"{eta_delta:.0f} min"
    st.markdown(
        f"""
        <div class="ws-summary">
          <div class="ws-summary-item">
            <div class="ws-summary-item-label">Detour for safety</div>
            <div class="ws-summary-item-val">{detour_str}</div>
          </div>
          <div class="ws-summary-item">
            <div class="ws-summary-item-label">Safety gain</div>
            <div class="ws-summary-item-val" style="color:#53E3A6">+{safety_gain}</div>
          </div>
          <div class="ws-summary-item">
            <div class="ws-summary-item-label">Time cost</div>
            <div class="ws-summary-item-val">{eta_str}</div>
          </div>
          <div class="ws-summary-item">
            <div class="ws-summary-item-label">Risk km avoided</div>
            <div class="ws-summary-item-val" style="color:#3DA9FC">{risk_avoided:.1f} km</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


_DOW_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def render_forecast_card(forecast, when, *, location_label: str = "your location") -> None:
    """Headline forecast card: risk gauge + confidence + top categories + WHY chips.

    `forecast` is a `forecast.ForecastResult`. `when` is a datetime.
    """
    risk_pct = int(round(max(0.0, min(1.0, forecast.risk)) * 100))
    color = forecast_color(forecast.risk)
    conf_cls = forecast.confidence  # "low" | "medium" | "high"
    cats = "".join(
        f'<span class="ws-fc-pill cat">{c} · {p:.0%}</span>'
        for c, p in forecast.top_categories[:3]
    )
    when_str = f"{_DOW_NAMES[when.weekday()]} {when.strftime('%H:%M')}"
    explain = (
        " · ".join(forecast.explain) if forecast.explain else
        f"Forecast for {location_label} at {when_str}"
    )
    st.markdown(
        f"""
        <div class="ws-fc-card">
          <div class="ws-fc-ring" style="--pct:{risk_pct}; --ring:{color};">
            <div class="ws-fc-ring-inner">
              <div class="ws-fc-ring-val">{risk_pct}</div>
              <div class="ws-fc-ring-band">forecast risk</div>
            </div>
          </div>
          <div style="flex:1; min-width:0;">
            <div class="ws-fc-meta-label">Forecast for {location_label} · {when_str}</div>
            <div class="ws-fc-meta-val" style="margin: 4px 0 8px;">
              <span class="ws-fc-pill {conf_cls}">{conf_cls.upper()} CONFIDENCE</span>
              <span style="color:#D4DAEA; font-weight:600; font-size:.85rem;">
                λ̂ = {forecast.expected_count:.2f} · cell obs {forecast.cell_obs:.1f}
              </span>
            </div>
            <div style="margin-bottom: 8px;">{cats}</div>
            <div style="font-size:.78rem; color:#8892A6; line-height:1.4;">{explain}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_24h_curve(curve, *, peak_color: str | None = None, label: str = "") -> None:
    """24-bar mini chart driven by 24 risk values in [0,1]."""
    if not curve:
        return
    peak = max(curve)
    if peak <= 0:
        peak = 1.0
    peak_idx = curve.index(peak) if peak > 0 else -1
    bars = []
    for h, r in enumerate(curve):
        height = max(2, int(round((r / peak) * 70))) if peak > 0 else 2
        col = forecast_color(r)
        cls = "ws-fc-bar peak" if h == peak_idx else "ws-fc-bar"
        bars.append(
            f'<div class="{cls}" style="height:{height}px; --bar:{col};" title="{h:02d}:00 — risk {r:.2f}"></div>'
        )
    label_html = f'<div class="ws-fc-meta-label" style="margin-bottom:6px;">{label}</div>' if label else ""
    st.markdown(
        label_html
        + f'<div class="ws-fc-bars">{"".join(bars)}</div>'
        + '<div class="ws-fc-axis"><span>00</span><span>06</span><span>12</span><span>18</span><span>23</span></div>',
        unsafe_allow_html=True,
    )


def render_category_bars(top_cats, label: str = "Expected categories") -> None:
    if not top_cats:
        return
    rows = []
    for c, p in top_cats[:3]:
        pct = max(0.0, min(1.0, p))
        rows.append(
            f"""
            <div class="ws-fc-cat">
              <div class="ws-fc-cat-name">{c}</div>
              <div class="ws-fc-cat-bar"><div class="ws-fc-cat-fill" style="width:{pct*100:.0f}%;"></div></div>
              <div class="ws-fc-cat-pct">{pct*100:.0f}%</div>
            </div>
            """
        )
    st.markdown(
        f'<div class="ws-fc-meta-label" style="margin-bottom:6px;">{label}</div>'
        + "".join(rows),
        unsafe_allow_html=True,
    )


def render_best_window(windows, your_time, *, top_k: int = 4) -> None:
    """Recommendation card.

    `windows` is the list returned by `find_best_departure` already sorted
    by safety descending: List[(datetime, RouteResult)].
    `your_time` is the user-chosen departure datetime.
    """
    if not windows:
        return
    your_match = next((r for t, r in windows if abs((t - your_time).total_seconds()) < 60), None)
    rows_html = []
    for i, (t, r) in enumerate(windows[:top_k]):
        delta_min = int(round((t - your_time).total_seconds() / 60))
        sign = "+" if delta_min >= 0 else ""
        is_best = (i == 0)
        is_yours = your_match is not None and abs((t - your_time).total_seconds()) < 60
        tag = (
            '<span class="ws-fc-window-tag best">SAFEST</span>'
            if is_best else
            '<span class="ws-fc-window-tag your">YOUR PICK</span>' if is_yours else ""
        )
        rows_html.append(
            f"""
            <div class="ws-fc-window-row">
              <div>
                <div class="ws-fc-window-time">{t.strftime('%a %H:%M')} {tag}</div>
                <div class="ws-fc-window-meta">{sign}{delta_min} min vs your time · safety {r.avg_safety} · min {r.min_safety} · {r.max_risk_segment_km:.1f} risk-km</div>
              </div>
              <div class="ws-route-mini-ring" style="--pct:{r.avg_safety}; --accent:{ROUTE_ACCENT['forecast-safest']};">
                <span>{r.avg_safety}</span>
              </div>
            </div>
            """
        )
    headline = ""
    if your_match is not None:
        gain = windows[0][1].avg_safety - your_match.avg_safety
        if gain >= 4:
            best_t = windows[0][0]
            delta = int(round((best_t - your_time).total_seconds() / 60))
            headline = (
                f'<div style="font-size:.95rem; font-weight:700; color:#5EEAD4; margin-bottom:8px;">'
                f'⏱ Shift departure to {best_t.strftime("%H:%M")} ({"+%d" % delta if delta >= 0 else delta} min) for +{gain} safety pts</div>'
            )
        else:
            headline = (
                '<div style="font-size:.85rem; color:#8892A6; margin-bottom:8px;">'
                'Your chosen time is already near-optimal — within 4 safety points of the best window.</div>'
            )
    st.markdown(
        f"""
        <div class="ws-fc-window">
          <div class="ws-fc-meta-label" style="margin-bottom:8px;">Best departure window</div>
          {headline}
          {''.join(rows_html)}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_hotspots(hotspots, *, label: str = "Forecasted hotspots") -> None:
    if not hotspots:
        return
    rows = []
    for i, h in enumerate(hotspots, start=1):
        risk = h["risk"]
        col = forecast_color(risk)
        rows.append(
            f"""
            <div class="ws-hotspot-row">
              <div class="ws-hotspot-rank">{i}</div>
              <div>
                <div class="ws-hotspot-coord">{h['lat']:.4f}, {h['lon']:.4f}</div>
                <div class="ws-hotspot-meta">top hazard: <b style="color:#C8B8FF; text-transform:capitalize;">{h['top_category']}</b> · {h['incidents']} historic · weight {h['observed_weight']}</div>
              </div>
              <div class="ws-hotspot-risk" style="color:{col};">{risk*100:.0f}</div>
            </div>
            """
        )
    st.markdown(
        f'<div class="ws-fc-meta-label" style="margin-bottom:8px;">{label}</div>'
        + "".join(rows),
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


# ----------------------------- Live Trip Companion -----------------------------


_STATUS_LABEL = {
    "active":    "live",
    "paused":    "paused",
    "completed": "arrived",
    "cancelled": "cancelled",
}


def _fmt_eta_min(minutes: float) -> str:
    minutes = max(0.0, minutes)
    if minutes < 1.0:
        return "<1 min"
    if minutes < 60:
        return f"{minutes:.0f} min"
    h = int(minutes // 60); m = int(round(minutes - 60 * h))
    return f"{h}h {m:02d}m"


def _rel_time(ts, now) -> str:
    if ts is None:
        return ""
    s = (now - ts).total_seconds()
    if s < 0:
        return "just now"
    if s < 60:
        return f"{int(s)}s ago"
    if s < 3600:
        return f"{int(s/60)}m ago"
    if s < 86400:
        return f"{int(s/3600)}h ago"
    return f"{int(s/86400)}d ago"


def render_live_trip_header(trip, now) -> None:
    """The big hero card at the top of the Live Trip tab."""
    pct = max(0, min(100, trip.progress_pct))
    eta_str = _fmt_eta_min(trip.eta_remaining_min)
    here_band = "live" if trip.status == "active" else _STATUS_LABEL.get(trip.status, trip.status)
    pulse_cls = trip.status if trip.status in ("paused", "completed", "cancelled") else ""
    accent = "#5EEAD4" if trip.status == "active" else (
        "#7BE7C2" if trip.status == "completed" else
        ("#FFA17A" if trip.status == "cancelled" else MUTED)
    )
    started = trip.started_at.strftime("%H:%M")
    arrive = (trip.expected_arrival or trip.arrived_at)
    arrive_str = arrive.strftime("%H:%M") if arrive else "—"

    st.markdown(
        f"""
        <div class="ws-live-head">
          <div class="ws-live-progress" style="--pct:{pct}; --accent:{accent};">
            <div class="ws-live-progress-inner">
              <div class="ws-live-progress-pct">{pct}%</div>
              <div class="ws-live-progress-cap">complete</div>
            </div>
          </div>
          <div class="ws-live-meta">
            <div style="display:flex; align-items:center; gap:10px;">
              <span class="ws-live-status-pulse {pulse_cls}"><span class="ws-dot"></span>{here_band}</span>
              <span class="ws-live-route">{trip.plan.route_mode.upper()} ROUTE · {trip.plan.distance_km:g} KM TOTAL</span>
            </div>
            <div class="ws-live-title">{trip.plan.origin_label} → {trip.plan.dest_label}</div>
            <div class="ws-live-stats">
              <div class="ws-live-stat">
                <div class="ws-live-stat-label">ETA</div>
                <div class="ws-live-stat-val">{eta_str}</div>
              </div>
              <div class="ws-live-stat">
                <div class="ws-live-stat-label">Distance left</div>
                <div class="ws-live-stat-val">{trip.distance_remaining_km:.2f} <span style="font-size:.7rem;color:{MUTED}">km</span></div>
              </div>
              <div class="ws-live-stat">
                <div class="ws-live-stat-label">Started</div>
                <div class="ws-live-stat-val">{started}</div>
              </div>
              <div class="ws-live-stat">
                <div class="ws-live-stat-label">Arrival</div>
                <div class="ws-live-stat-val">{arrive_str}</div>
              </div>
            </div>
            <div class="ws-live-bar-track"><div class="ws-live-bar-fill" style="width:{pct}%"></div></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_alert_feed(alerts, now, *, limit: int = 8) -> None:
    if not alerts:
        st.markdown(
            "<div class='ws-look-card' style='color:#8892A6; font-size:.82rem;'>"
            "No alerts yet. WaySafe will warn you as soon as it sees one — geofence "
            "crossings, risk corridors ahead, stalls, or arrival.</div>",
            unsafe_allow_html=True,
        )
        return
    rows = []
    for a in list(reversed(alerts))[:limit]:
        sev = a.severity if a.severity in ("info", "warn", "critical") else "info"
        rows.append(
            f"<div class='ws-alert {sev}'>"
            f"<div class='ws-alert-icon'>{a.icon}</div>"
            f"<div class='ws-alert-msg'>{a.message}</div>"
            f"<div class='ws-alert-time'>{_rel_time(a.ts, now)}</div>"
            "</div>"
        )
    st.markdown(
        "<div class='ws-alert-feed'>" + "".join(rows) + "</div>",
        unsafe_allow_html=True,
    )


def render_lookahead_panel(samples, *, label: str = "Risk on the next 1.5 km") -> None:
    """`samples` is `[(km_offset, risk_0_1, [hazard_label]), ...]`."""
    if not samples:
        st.markdown(
            f"<div class='ws-look-card'><div class='ws-kicker'>{label}</div>"
            "<div style='color:#8892A6; font-size:.82rem; margin-top:6px'>"
            "Not enough route ahead to scan.</div></div>",
            unsafe_allow_html=True,
        )
        return
    rows = []
    for dk, risk, hazard in samples:
        risk = max(0.0, min(1.0, float(risk)))
        tone = forecast_color(risk)
        d_label = f"+{dk*1000:.0f} m" if dk < 1 else f"+{dk:.1f} km"
        haz = f"<div style='font-size:.66rem;color:{MUTED}'>{hazard}</div>" if hazard else ""
        rows.append(
            f"<div class='ws-look-row'>"
            f"<div><div class='ws-look-d'>{d_label}</div>{haz}</div>"
            f"<div class='ws-look-bar'><div class='ws-look-fill' style='--tone:{tone}; width:{risk*100:.0f}%'></div></div>"
            f"<div class='ws-look-pct' style='--tone:{tone}'>{int(risk*100)}</div>"
            "</div>"
        )
    st.markdown(
        f"<div class='ws-look-card'><div class='ws-kicker'>{label}</div>"
        + "".join(rows) + "</div>",
        unsafe_allow_html=True,
    )


def _avatar_palette(seed: str) -> tuple[str, str]:
    palettes = [
        ("#5EEAD4", "#A78BFA"), ("#F9C440", "#FF6A3D"),
        ("#3DA9FC", "#5EEAD4"), ("#FF6A3D", "#FF3D60"),
        ("#7BE7C2", "#3DA9FC"), ("#A78BFA", "#FF6A3D"),
    ]
    h = sum(ord(c) for c in seed)
    return palettes[h % len(palettes)]


def render_contacts_strip(contacts) -> None:
    if not contacts:
        st.markdown(
            "<div style='color:#8892A6; font-size:.82rem;'>No trusted contacts yet — "
            "add one below so WaySafe can ping them on departure, arrival, and SOS.</div>",
            unsafe_allow_html=True,
        )
        return
    chips = []
    for c in contacts:
        c1, c2 = _avatar_palette(c.id)
        initials = "".join(p[0].upper() for p in c.name.split()[:2]) or "?"
        chips.append(
            f"<div class='ws-contact'>"
            f"<div class='ws-contact-avatar' style='--c1:{c1}; --c2:{c2}'>{initials}</div>"
            f"<div><div class='ws-contact-name'>{c.name}</div>"
            f"<div class='ws-contact-rel'>{c.relationship} · {len(c.opt_in)} alerts opt-in</div></div>"
            "</div>"
        )
    st.markdown("".join(chips), unsafe_allow_html=True)


def render_broadcast_log(broadcasts, now, *, limit: int = 12) -> None:
    if not broadcasts:
        st.markdown(
            "<div style='color:#8892A6; font-size:.8rem;'>No simulated dispatches yet.</div>",
            unsafe_allow_html=True,
        )
        return
    rows = []
    for b in list(reversed(broadcasts))[:limit]:
        kind_cls = b.kind if b.kind in ("auto_sos", "departure", "arrival") else "info"
        c1, c2 = _avatar_palette(b.contact_id)
        initials = "".join(p[0].upper() for p in b.contact_name.split()[:2]) or "?"
        rows.append(
            f"<div class='ws-broadcast-row'>"
            f"<div class='ws-contact-avatar' style='--c1:{c1}; --c2:{c2}; width:24px; height:24px; font-size:.6rem;'>{initials}</div>"
            f"<div>"
            f"<span class='ws-broadcast-kind {kind_cls}'>{b.kind}</span>"
            f"<div class='ws-broadcast-name'>→ {b.contact_name} <span style='color:{MUTED}; font-weight:500;'>· {b.contact}</span></div>"
            f"<div class='ws-broadcast-body'>{b.body}</div>"
            "</div>"
            f"<div class='ws-broadcast-time'>{_rel_time(b.ts, now)}</div>"
            "</div>"
        )
    st.markdown("".join(rows), unsafe_allow_html=True)


def render_trip_empty(*, hint: str = "Plan a route in the **Plan Route** tab, then come back here to start the journey.") -> None:
    st.markdown(
        f"""
        <div class='ws-trip-empty'>
          <div class='ws-trip-empty-icon'>🧭</div>
          <h4>No active journey</h4>
          <p>{hint}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_trip_log_row(digest: dict, now) -> None:
    counts = digest.get("alerts_by_kind", {}) or {}
    sos_pill = (f"<span class='ws-mini-pill' style='color:#FF6680; border-color:rgba(255,61,96,0.36); background:rgba(255,61,96,0.10);'>SOS</span>"
                if digest.get("auto_sos_fired") or digest.get("user_sos_fired") else "")
    pills = "".join(
        f"<span class='ws-mini-pill'>{k} · {v}</span>"
        for k, v in counts.items() if k not in ("departure", "arrival")
    ) or "<span class='ws-mini-pill'>no warnings</span>"
    started = digest.get("started_at", "")[:16].replace("T", " ")
    pct = digest.get("progress_pct", 0)
    status = digest.get("status", "")
    status_color = {"completed": "#7BE7C2", "cancelled": "#FFA17A",
                    "active": "#5EEAD4", "paused": MUTED}.get(status, MUTED)
    st.markdown(
        f"""
        <div class='ws-trip-log-row'>
          <div>
            <div class='ws-trip-log-title'>{digest.get('origin','?')} → {digest.get('destination','?')}</div>
            <div class='ws-trip-log-meta'>{started} · {digest.get('route_mode','—')} · {digest.get('km_travelled', 0)} / {digest.get('distance_km', 0)} km · <span style='color:{status_color}; font-weight:700;'>{status}</span></div>
            <div class='ws-trip-log-stats' style='margin-top:6px;'>{sos_pill}{pills}</div>
          </div>
          <div style='text-align:right;'>
            <div style='font-size:1.4rem; font-weight:800; color:{status_color};'>{pct}%</div>
            <div style='font-size:.62rem; letter-spacing:.12em; text-transform:uppercase; color:{MUTED};'>complete</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
