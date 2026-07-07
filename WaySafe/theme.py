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

        /* ---------- Multi-stop Itinerary (Day 21) ---------- */
        .ws-itin-hero {{
            background: linear-gradient(135deg, rgba(94,234,212,0.10) 0%, rgba(167,139,250,0.10) 100%);
            border: 1px solid rgba(255,255,255,0.07);
            border-radius: 18px; padding: 18px 22px; margin-bottom: 14px;
            display: grid; grid-template-columns: auto 1fr auto; gap: 22px; align-items: center;
        }}
        .ws-itin-hero-ring {{
            width: 108px; height: 108px; border-radius: 50%;
            display:flex; align-items:center; justify-content:center; position: relative; flex-shrink: 0;
            background: conic-gradient(var(--ring) calc(var(--pct) * 1%), rgba(255,255,255,0.06) 0);
        }}
        .ws-itin-hero-ring::after {{
            content:""; position:absolute; inset:9px; background:{CARD}; border-radius:50%;
        }}
        .ws-itin-hero-ring-inner {{ position:relative; z-index:1; text-align:center; }}
        .ws-itin-hero-ring-val {{ font-size: 1.85rem; font-weight: 800; line-height: 1; }}
        .ws-itin-hero-ring-lbl {{
            font-size:.58rem; letter-spacing:.14em; text-transform:uppercase; color:{MUTED};
            font-weight:700; margin-top:4px;
        }}
        .ws-itin-hero-title {{ font-size: 1.18rem; font-weight: 800; letter-spacing:-0.01em; margin-bottom:2px; }}
        .ws-itin-hero-sub   {{ font-size: .78rem; color: {MUTED}; }}
        .ws-itin-hero-stats {{ display:flex; gap: 18px; margin-top: 12px; flex-wrap: wrap; }}
        .ws-itin-hero-stat  {{ }}
        .ws-itin-hero-stat-lbl {{
            font-size:.58rem; letter-spacing:.14em; text-transform:uppercase; color:{MUTED}; font-weight:700;
        }}
        .ws-itin-hero-stat-val {{ font-size:1.05rem; font-weight:800; }}
        .ws-itin-hero-stat-val small {{ font-size:.62rem; color:{MUTED}; font-weight:600; }}
        .ws-itin-hero-bands  {{ display:flex; flex-direction:column; gap:6px; }}
        .ws-itin-hero-band   {{
            display:inline-flex; align-items:center; gap:8px;
            font-size:.7rem; color:#D4DAEA; font-weight:600;
        }}
        .ws-itin-hero-band-dot {{ width:8px; height:8px; border-radius:50%; }}

        .ws-itin-gantt {{
            background:{CARD}; border:1px solid rgba(255,255,255,0.06);
            border-radius:14px; padding:14px 18px; margin-bottom: 12px;
        }}
        .ws-itin-gantt-hdr {{
            display:flex; justify-content:space-between; align-items:baseline; margin-bottom:10px;
        }}
        .ws-itin-gantt-hdr h4 {{ margin:0; font-weight:800; font-size:.95rem; letter-spacing:-0.01em; }}
        .ws-itin-gantt-hdr .ws-itin-gantt-span {{
            font-size:.7rem; color:{MUTED}; font-variant-numeric: tabular-nums;
        }}
        .ws-itin-gantt-ruler {{
            position:relative; height: 18px; margin-bottom: 6px;
            border-bottom:1px dashed rgba(255,255,255,0.10);
        }}
        .ws-itin-gantt-tick {{
            position:absolute; top:0; bottom:0;
            font-size:.62rem; color:{MUTED}; font-variant-numeric: tabular-nums;
            transform:translateX(-50%); white-space: nowrap;
        }}
        .ws-itin-gantt-row {{
            position:relative; height: 32px; margin-bottom: 4px;
            background: rgba(255,255,255,0.02);
            border-radius: 8px;
            display:flex; align-items:center;
        }}
        .ws-itin-gantt-row-lbl {{
            position:absolute; left:10px; top:50%; transform:translateY(-50%);
            font-size:.7rem; font-weight:700; color:#D4DAEA; z-index: 4;
            text-shadow: 0 1px 2px rgba(0,0,0,0.5); pointer-events:none;
            max-width: 40%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
        }}
        .ws-itin-gantt-bar {{
            position:absolute; top:6px; bottom:6px;
            border-radius: 6px;
            box-shadow: inset 0 0 0 1px rgba(255,255,255,0.10), 0 1px 4px rgba(0,0,0,0.25);
            display:flex; align-items:center; padding: 0 10px;
            font-size:.66rem; color:rgba(255,255,255,0.92); font-weight:700;
            font-variant-numeric: tabular-nums;
            white-space:nowrap; overflow:hidden;
        }}
        .ws-itin-gantt-bar.dwell {{
            background: repeating-linear-gradient(
                45deg, rgba(94,234,212,0.20) 0 6px, rgba(94,234,212,0.05) 6px 12px
            );
            border:1px solid rgba(94,234,212,0.35);
            color:#7EE7DA;
        }}

        .ws-itin-leg {{
            background:{CARD}; border:1px solid rgba(255,255,255,0.06);
            border-left: 3px solid var(--accent, #3DA9FC);
            border-radius:12px; padding: 12px 16px; margin-bottom: 8px;
        }}
        .ws-itin-leg-hdr {{
            display:flex; justify-content:space-between; align-items:center; gap: 10px;
        }}
        .ws-itin-leg-title {{
            font-size:.92rem; font-weight:800; color:#E6ECF7; letter-spacing:-0.01em;
        }}
        .ws-itin-leg-time {{
            font-size:.7rem; color:{MUTED}; font-variant-numeric: tabular-nums;
        }}
        .ws-itin-leg-bar-track {{
            height:5px; background:rgba(255,255,255,0.05); border-radius:3px;
            margin-top:8px; overflow:hidden;
        }}
        .ws-itin-leg-bar-fill {{
            height:100%; border-radius:3px;
            background: linear-gradient(90deg, #FF3D60 0%, #FF7F50 25%, #F9C440 55%, #53E3A6 90%);
        }}
        .ws-itin-leg-stats {{
            display:grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-top:10px;
        }}
        .ws-itin-leg-stat {{ background: rgba(255,255,255,0.03); border-radius:8px; padding: 6px 10px; }}
        .ws-itin-leg-stat-lbl {{
            font-size:.56rem; letter-spacing:.14em; text-transform:uppercase; color:{MUTED}; font-weight:700;
        }}
        .ws-itin-leg-stat-val {{ font-size:.95rem; font-weight:800; color:#E6ECF7; }}
        .ws-itin-leg-stat-val small {{ font-size:.6rem; color:{MUTED}; font-weight:600; }}
        .ws-itin-leg-safety {{
            display:inline-flex; align-items:center; gap:6px; padding:2px 10px; border-radius:999px;
            font-size:.68rem; font-weight:800; letter-spacing:.02em;
        }}
        .ws-itin-empty {{
            background:{CARD}; border: 1px dashed rgba(255,255,255,0.12);
            border-radius:14px; padding: 32px 22px; text-align:center;
        }}
        .ws-itin-empty-icon {{ font-size: 2.4rem; margin-bottom: 6px; }}
        .ws-itin-empty h4 {{ margin: 0 0 4px; font-weight:800; }}
        .ws-itin-empty p  {{ color:{MUTED}; font-size:.82rem; margin: 0; }}
        .ws-itin-window-row {{
            display:flex; align-items:center; gap:12px; padding: 8px 12px;
            background: rgba(255,255,255,0.02); border:1px solid rgba(255,255,255,0.06);
            border-radius: 10px; margin-bottom: 6px;
        }}
        .ws-itin-window-time {{ font-weight:800; font-size:.85rem; color:#D4DAEA;
            font-variant-numeric: tabular-nums; min-width: 92px; }}
        .ws-itin-window-delta {{ font-size:.66rem; color:{MUTED}; min-width: 72px; }}
        .ws-itin-window-bar {{ flex:1; height:8px; background:rgba(255,255,255,0.05); border-radius:4px; overflow:hidden; }}
        .ws-itin-window-fill {{ height:100%; border-radius:4px;
            background: linear-gradient(90deg, var(--accent, #53E3A6), rgba(255,255,255,0.12));
        }}
        .ws-itin-window-score {{ font-weight:800; font-variant-numeric: tabular-nums; min-width: 36px; text-align:right; }}

        /* ===== Sentinel — live risk-pulse + cluster cards ===== */
        .ws-sent-hero {{
            position: relative;
            background: linear-gradient(135deg, rgba(22,26,35,0.95) 0%, rgba(14,17,23,0.95) 100%);
            border: 1px solid rgba(255,255,255,0.06);
            border-radius: 18px;
            padding: 22px 26px;
            overflow: hidden;
            margin-bottom: 14px;
        }}
        .ws-sent-hero-glow {{
            position: absolute; inset: -40%;
            background: radial-gradient(circle at 35% 0%, var(--pulse-glow, rgba(83,227,166,0.18)) 0%, transparent 60%);
            z-index: 0; pointer-events: none;
        }}
        .ws-sent-hero-inner {{
            position: relative; z-index: 1;
            display: flex; align-items: center; gap: 24px; flex-wrap: wrap;
        }}
        .ws-sent-pulse-dot {{
            width: 88px; height: 88px; border-radius: 50%;
            background: radial-gradient(circle, var(--pulse-hue, #53E3A6) 0%, rgba(0,0,0,0) 72%);
            display: flex; align-items: center; justify-content: center;
            color: #0E1117; font-weight: 900; font-size: .9rem; letter-spacing: .06em;
            position: relative;
            flex-shrink: 0;
        }}
        .ws-sent-pulse-dot::before, .ws-sent-pulse-dot::after {{
            content:""; position:absolute; inset: 18px;
            border-radius: 50%;
            border: 2px solid var(--pulse-hue, #53E3A6);
            animation: ws-sent-pulse 2.4s infinite ease-out;
            opacity: 0;
        }}
        .ws-sent-pulse-dot::after {{ animation-delay: 1.2s; }}
        @keyframes ws-sent-pulse {{
            0%   {{ transform: scale(.85); opacity: .8; }}
            70%  {{ transform: scale(1.9); opacity: 0; }}
            100% {{ transform: scale(1.9); opacity: 0; }}
        }}
        .ws-sent-pulse-core {{
            width: 32px; height: 32px; border-radius: 50%;
            background: var(--pulse-hue, #53E3A6);
            box-shadow: 0 0 18px var(--pulse-hue, #53E3A6);
            z-index: 1;
        }}
        .ws-sent-status-block {{ display: flex; flex-direction: column; min-width: 180px; }}
        .ws-sent-status-kicker {{
            font-size: .68rem; letter-spacing: .14em; text-transform: uppercase;
            color: {MUTED}; font-weight: 700;
        }}
        .ws-sent-status-label {{
            font-size: 1.85rem; font-weight: 800; line-height: 1.05; letter-spacing: -0.02em;
            color: var(--pulse-hue, #53E3A6);
            margin-top: 2px;
        }}
        .ws-sent-headline {{ color: #C7CDDC; font-size: .88rem; margin-top: 3px; }}
        .ws-sent-stats {{ display: flex; gap: 26px; margin-left: auto; flex-wrap: wrap; }}
        .ws-sent-stat {{ text-align: center; min-width: 64px; }}
        .ws-sent-stat-val {{
            font-weight: 800; font-size: 1.5rem; line-height: 1; color: #E6E9F2;
            font-variant-numeric: tabular-nums;
        }}
        .ws-sent-stat-lbl {{
            font-size: .62rem; letter-spacing: .14em; text-transform: uppercase;
            color: {MUTED}; margin-top: 4px;
        }}
        .ws-sent-counters {{
            display: flex; gap: 8px; margin-top: 14px; flex-wrap: wrap;
            position: relative; z-index: 1;
        }}
        .ws-sent-chip {{
            display: inline-flex; gap: 6px; align-items: center;
            padding: 4px 10px; border-radius: 999px; font-size: .72rem; font-weight: 700;
            background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.07);
            color: #D4DAEA;
        }}
        .ws-sent-chip-dot {{ width: 8px; height: 8px; border-radius: 50%; }}

        /* Cluster card */
        .ws-sent-cluster {{
            background: {CARD}; border: 1px solid rgba(255,255,255,0.06); border-radius: 14px;
            padding: 14px 16px; margin-bottom: 10px; position: relative;
            border-left: 3px solid var(--accent, #53E3A6);
        }}
        .ws-sent-cluster-head {{ display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }}
        .ws-sent-cluster-icon {{ font-size: 1.55rem; line-height: 1; }}
        .ws-sent-cluster-title {{ font-weight: 800; font-size: 1.05rem; color: #E6E9F2; }}
        .ws-sent-cluster-sub {{ color: {MUTED}; font-size: .76rem; margin-top: 2px; }}
        .ws-sent-cluster-status {{
            margin-left: auto;
            padding: 3px 12px; border-radius: 999px; font-size: .66rem; font-weight: 800;
            letter-spacing: .12em; text-transform: uppercase;
            background: var(--accent-bg, rgba(83,227,166,0.14));
            color: var(--accent, #53E3A6);
            border: 1px solid var(--accent-bd, rgba(83,227,166,0.32));
        }}

        .ws-sent-velbar-wrap {{ margin-top: 12px; position: relative; padding-top: 14px; }}
        .ws-sent-velbar {{
            height: 7px; background: rgba(255,255,255,0.05);
            border-radius: 4px; overflow: hidden; position: relative;
        }}
        .ws-sent-velbar-fill {{
            height: 100%; border-radius: 4px;
            background: linear-gradient(90deg, var(--accent), rgba(255,255,255,0.12));
        }}
        .ws-sent-velbar-baseline {{
            position: absolute; top: 12px; bottom: 1px;
            width: 2px; background: rgba(255,255,255,0.42);
            border-radius: 1px;
        }}
        .ws-sent-velbar-baseline-lbl {{
            position: absolute; top: -2px; font-size: .56rem; font-weight: 700;
            color: rgba(255,255,255,0.55); letter-spacing: .05em;
            transform: translateX(-50%);
        }}
        .ws-sent-vel-meta {{
            display: flex; justify-content: space-between;
            font-size: .68rem; color: {MUTED}; margin-top: 6px;
        }}
        .ws-sent-vel-current {{ color: var(--accent, #53E3A6); font-weight: 700; }}

        .ws-sent-statgrid {{
            display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 12px;
        }}
        .ws-sent-statgrid-cell {{
            background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.04);
            border-radius: 8px; padding: 8px 10px;
        }}
        .ws-sent-statgrid-val {{
            font-weight: 800; font-size: 1.05rem; color: #E6E9F2;
            font-variant-numeric: tabular-nums;
        }}
        .ws-sent-statgrid-lbl {{
            font-size: .58rem; letter-spacing: .1em; text-transform: uppercase;
            color: {MUTED}; margin-top: 2px;
        }}

        .ws-sent-spark-wrap {{
            margin-top: 12px; padding-top: 10px;
            border-top: 1px dashed rgba(255,255,255,0.06);
        }}
        .ws-sent-spark-kicker {{
            font-size: .58rem; letter-spacing: .1em; text-transform: uppercase;
            color: {MUTED}; margin-bottom: 6px;
        }}
        .ws-sent-sparkline {{
            display: flex; align-items: flex-end; gap: 1px; height: 30px;
        }}
        .ws-sent-spark-bar {{
            flex: 1; min-height: 2px;
            background: var(--accent);
            border-radius: 1px 1px 0 0; opacity: 0.85;
        }}
        .ws-sent-spark-bar.empty {{ background: rgba(255,255,255,0.04); opacity: 1; }}
        .ws-sent-spark-axis {{
            display: flex; justify-content: space-between;
            font-size: .55rem; color: {MUTED}; margin-top: 3px;
        }}

        .ws-sent-mix {{ display: flex; gap: 6px; margin-top: 10px; flex-wrap: wrap; }}
        .ws-sent-mix-tag {{
            padding: 2px 9px; border-radius: 999px; font-size: .68rem;
            background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.07);
            color: #C7CDDC;
        }}

        .ws-sent-action {{
            margin-top: 12px; padding: 9px 14px; border-radius: 10px;
            background: var(--action-bg, rgba(83,227,166,0.08));
            border-left: 2px solid var(--accent, #53E3A6);
            font-size: .84rem; color: #D4DAEA; line-height: 1.4;
        }}

        .ws-sent-empty {{
            background: rgba(83,227,166,0.05); border: 1px dashed rgba(83,227,166,0.28);
            border-radius: 14px; padding: 36px 20px; text-align: center; color: #B8C0D2;
            margin: 14px 0;
        }}
        .ws-sent-empty-title {{
            font-size: 1.15rem; font-weight: 800; color: #E6E9F2; margin-bottom: 6px;
            letter-spacing: -0.01em;
        }}

        /* Watch banner (Map tab) */
        .ws-sent-banner {{
            display: flex; align-items: center; gap: 12px;
            background: linear-gradient(90deg, var(--banner-bg, rgba(255,127,80,0.14)) 0%, rgba(0,0,0,0) 70%);
            border: 1px solid var(--banner-bd, rgba(255,127,80,0.30));
            border-left: 4px solid var(--banner-hue, #FF7F50);
            border-radius: 10px;
            padding: 10px 14px; margin-bottom: 10px;
        }}
        .ws-sent-banner-icon {{ font-size: 1.4rem; line-height: 1; }}
        .ws-sent-banner-text {{ font-weight: 700; color: #E6E9F2; flex: 1; }}
        .ws-sent-banner-text small {{ font-weight: 500; color: {MUTED}; margin-left: 8px; }}
        .ws-sent-banner-meta {{ color: {MUTED}; font-size: .78rem; }}

        /* ----------------------------- Travel Advisory ----------------------------- */
        .ws-adv-hero {{
            position: relative; overflow: hidden;
            border-radius: 18px; padding: 22px 24px;
            background:
                radial-gradient(900px 280px at -10% -40%, var(--adv-glow, rgba(255,127,80,0.22)) 0%, transparent 60%),
                linear-gradient(180deg, rgba(255,255,255,0.02) 0%, rgba(255,255,255,0) 100%),
                #161A23;
            border: 1px solid rgba(255,255,255,0.06);
            border-left: 6px solid var(--adv-hue, #FF7F50);
            box-shadow: 0 14px 38px rgba(0,0,0,0.35);
            margin-bottom: 16px;
        }}
        .ws-adv-hero::before {{
            content: ""; position: absolute; right: -120px; top: -90px;
            width: 380px; height: 380px; border-radius: 50%;
            background: radial-gradient(closest-side, var(--adv-glow, rgba(255,127,80,0.22)), transparent 70%);
            pointer-events: none;
        }}
        .ws-adv-hero-inner {{ position: relative; display: flex; gap: 26px; align-items: center; }}
        .ws-adv-stripe {{
            display: inline-flex; align-items: center; gap: 8px;
            padding: 5px 12px; border-radius: 999px;
            background: var(--adv-stripe-bg, rgba(255,127,80,0.16));
            border: 1px solid var(--adv-stripe-bd, rgba(255,127,80,0.32));
            color: var(--adv-hue, #FF7F50); font-weight: 800;
            font-size: .72rem; letter-spacing: .14em; text-transform: uppercase;
        }}
        .ws-adv-stripe-dot {{
            width: 8px; height: 8px; border-radius: 50%;
            background: var(--adv-hue, #FF7F50);
            box-shadow: 0 0 0 4px var(--adv-stripe-bd, rgba(255,127,80,0.32));
        }}
        .ws-adv-title {{
            font-size: 1.55rem; font-weight: 800; letter-spacing: -0.02em;
            color: #F2F4FA; margin: 10px 0 4px;
        }}
        .ws-adv-coords {{ color: {MUTED}; font-size: .82rem; }}
        .ws-adv-headline {{
            color: #D4DAEA; font-size: .95rem; line-height: 1.5;
            margin-top: 12px; max-width: 56ch;
        }}
        .ws-adv-tiles {{
            display: grid; grid-template-columns: repeat(4, 1fr);
            gap: 10px; margin: 14px 0 16px;
        }}
        .ws-adv-tile {{
            background: #1B1F2B; border: 1px solid rgba(255,255,255,0.06);
            border-radius: 12px; padding: 12px 14px;
        }}
        .ws-adv-tile-kicker {{
            color: {MUTED}; font-size: .68rem; letter-spacing: .12em;
            text-transform: uppercase; margin-bottom: 6px;
        }}
        .ws-adv-tile-val {{
            font-size: 1.35rem; font-weight: 800; letter-spacing: -0.02em;
            color: #F2F4FA; font-variant-numeric: tabular-nums;
        }}
        .ws-adv-tile-sub {{ color: {MUTED}; font-size: .78rem; margin-top: 2px; }}
        .ws-adv-section {{ margin: 18px 0 10px; }}
        .ws-adv-section-title {{
            display: flex; align-items: center; gap: 8px;
            color: #B8C0D2; font-size: .72rem; letter-spacing: .14em;
            text-transform: uppercase; font-weight: 700; margin-bottom: 8px;
        }}
        .ws-adv-inc-row {{
            display: flex; align-items: center; gap: 12px;
            background: #1B1F2B; border: 1px solid rgba(255,255,255,0.05);
            border-radius: 11px; padding: 10px 14px; margin-bottom: 6px;
        }}
        .ws-adv-inc-dot {{
            width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
            background: var(--inc-hue, #F9C440);
            box-shadow: 0 0 0 3px var(--inc-shadow, rgba(249,196,64,0.20));
        }}
        .ws-adv-inc-cat {{ font-weight: 700; color: #E6E9F2; min-width: 90px; }}
        .ws-adv-inc-dist {{ color: {MUTED}; font-variant-numeric: tabular-nums; min-width: 60px; }}
        .ws-adv-inc-when {{ color: {MUTED}; font-variant-numeric: tabular-nums; min-width: 70px; }}
        .ws-adv-inc-status {{
            font-size: .68rem; letter-spacing: .10em; text-transform: uppercase;
            padding: 3px 8px; border-radius: 999px; font-weight: 700;
        }}
        .ws-adv-inc-status.verified {{
            background: rgba(83,227,166,0.14); color: #5EEAD4;
            border: 1px solid rgba(83,227,166,0.30);
        }}
        .ws-adv-inc-status.pending {{
            background: rgba(249,196,64,0.14); color: #F9C440;
            border: 1px solid rgba(249,196,64,0.30);
        }}
        .ws-adv-inc-note {{ flex: 1; color: #B8C0D2; font-size: .85rem; font-style: italic; }}
        .ws-adv-spark {{ display: flex; align-items: flex-end; gap: 4px; height: 56px; padding-top: 4px; }}
        .ws-adv-spark-bar {{
            flex: 1; min-width: 6px; border-radius: 3px 3px 0 0;
            background: linear-gradient(180deg, var(--adv-hue, #FF7F50), rgba(255,255,255,0.05));
            transition: height .25s ease;
        }}
        .ws-adv-spark-empty {{ background: rgba(255,255,255,0.05); height: 4px; align-self: flex-end; }}
        .ws-adv-spark-labels {{
            display: flex; justify-content: space-between;
            color: {MUTED}; font-size: .72rem; margin-top: 4px;
        }}
        .ws-adv-cluster {{
            display: flex; align-items: center; gap: 10px;
            background: #1B1F2B; border: 1px solid rgba(255,255,255,0.05);
            border-radius: 11px; padding: 10px 14px; margin-bottom: 6px;
        }}
        .ws-adv-cluster-pill {{
            font-size: .68rem; letter-spacing: .10em; text-transform: uppercase;
            padding: 3px 9px; border-radius: 999px; font-weight: 800;
            background: var(--cluster-bg, rgba(249,196,64,0.14));
            color: var(--cluster-hue, #F9C440);
            border: 1px solid var(--cluster-bd, rgba(249,196,64,0.30));
        }}
        .ws-adv-window {{
            display: flex; align-items: center; gap: 10px;
            background: #1B1F2B; border: 1px solid rgba(255,255,255,0.05);
            border-radius: 11px; padding: 10px 14px; margin-bottom: 6px;
        }}
        .ws-adv-window-label {{ font-weight: 700; color: #E6E9F2; min-width: 100px; }}
        .ws-adv-window-bar {{
            flex: 1; height: 6px; border-radius: 3px;
            background: rgba(255,255,255,0.06); overflow: hidden;
        }}
        .ws-adv-window-bar-fill {{
            height: 100%; border-radius: 3px;
            background: linear-gradient(90deg, #53E3A6 0%, #F9C440 50%, #FF3D60 100%);
        }}
        .ws-adv-window-pct {{
            color: #B8C0D2; font-weight: 700; font-variant-numeric: tabular-nums;
            min-width: 50px; text-align: right;
        }}
        .ws-adv-poi {{
            display: flex; align-items: center; gap: 10px;
            padding: 8px 14px; border-bottom: 1px solid rgba(255,255,255,0.04);
        }}
        .ws-adv-poi:last-child {{ border-bottom: none; }}
        .ws-adv-poi-icon {{
            width: 30px; height: 30px; border-radius: 8px;
            display: flex; align-items: center; justify-content: center;
            background: rgba(61,169,252,0.14); color: #5EEAD4; font-size: 1rem;
        }}
        .ws-adv-poi-name {{ flex: 1; color: #E6E9F2; font-weight: 600; }}
        .ws-adv-poi-type {{ color: {MUTED}; font-size: .76rem; text-transform: uppercase; letter-spacing: .08em; }}
        .ws-adv-poi-dist {{ color: #5EEAD4; font-variant-numeric: tabular-nums; font-weight: 700; }}
        .ws-adv-rec {{
            display: flex; gap: 12px; align-items: flex-start;
            background: linear-gradient(90deg, rgba(255,127,80,0.06), rgba(255,127,80,0.01));
            border-left: 3px solid var(--adv-hue, #FF7F50);
            border-radius: 10px; padding: 10px 14px; margin-bottom: 6px;
        }}
        .ws-adv-rec-num {{
            width: 22px; height: 22px; border-radius: 6px; flex-shrink: 0;
            display: flex; align-items: center; justify-content: center;
            background: var(--adv-hue, #FF7F50); color: #0E1117;
            font-weight: 800; font-size: .78rem;
        }}
        .ws-adv-rec-text {{ color: #D4DAEA; line-height: 1.45; flex: 1; }}
        .ws-adv-rec-text strong {{ color: #F2F4FA; }}
        .ws-adv-empty {{
            background: rgba(83,227,166,0.05); border: 1px dashed rgba(83,227,166,0.22);
            border-radius: 12px; padding: 18px 16px; text-align: center;
            color: #B8C0D2; font-size: .88rem; margin: 6px 0 10px;
        }}

        /* ---------- Compass — destination showdown ---------- */
        .ws-cmp-hero {{
            position: relative; overflow: hidden;
            display: flex; gap: 24px; align-items: center;
            background: {CARD}; border: 1px solid rgba(255,255,255,0.06);
            border-left: 6px solid var(--hue, {PRIMARY});
            border-radius: 16px; padding: 20px 24px; margin-bottom: 14px;
        }}
        .ws-cmp-hero::before {{
            content:""; position:absolute; inset:0;
            background: radial-gradient(120% 160% at 0% 0%, var(--glow, transparent) 0%, transparent 55%);
            pointer-events:none;
        }}
        .ws-cmp-hero-body {{ position: relative; flex: 1; min-width: 0; }}
        .ws-cmp-crown {{
            display:inline-flex; align-items:center; gap:6px;
            font-size:.72rem; font-weight:800; letter-spacing:.12em; text-transform:uppercase;
            color: var(--hue, {PRIMARY});
            background: rgba(255,255,255,0.04); border:1px solid var(--hue, {PRIMARY});
            border-radius:999px; padding:4px 12px; margin-bottom:8px;
        }}
        .ws-cmp-hero-title {{ font-size:1.5rem; font-weight:800; line-height:1.2; color:#F2F4FA; }}
        .ws-cmp-hero-detail {{ font-size:.95rem; color:#C7CEDE; margin-top:6px; }}
        .ws-cmp-hero-detail strong {{ color: var(--hue, {PRIMARY}); }}
        .ws-cmp-hero-meta {{ font-size:.78rem; color:{MUTED}; margin-top:10px; }}
        .ws-cmp-margin {{
            position:relative; text-align:center; flex-shrink:0;
            background: rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.08);
            border-radius:14px; padding:12px 18px; min-width:96px;
        }}
        .ws-cmp-margin-val {{ font-size:2rem; font-weight:800; color: var(--hue, {PRIMARY}); line-height:1; }}
        .ws-cmp-margin-lbl {{ font-size:.62rem; letter-spacing:.12em; text-transform:uppercase; color:{MUTED}; margin-top:4px; font-weight:700; }}

        .ws-cmp-podium {{ display:grid; gap:12px; margin-bottom:14px;
            grid-template-columns: repeat(auto-fit, minmax(168px, 1fr)); }}
        .ws-cmp-card {{
            background: {CARD}; border:1px solid rgba(255,255,255,0.06);
            border-radius:14px; padding:14px 16px; position:relative; overflow:hidden;
        }}
        .ws-cmp-card.is-winner {{
            border-color: var(--hue, {PRIMARY});
            box-shadow: 0 0 0 1px var(--hue, {PRIMARY}), 0 10px 30px -12px var(--hue, {PRIMARY});
        }}
        .ws-cmp-card-top {{ display:flex; align-items:center; justify-content:space-between; margin-bottom:8px; }}
        .ws-cmp-rank {{
            width:26px; height:26px; border-radius:8px; flex-shrink:0;
            display:flex; align-items:center; justify-content:center;
            font-weight:800; font-size:.82rem; color:#0E1117;
            background: rgba(255,255,255,0.16);
        }}
        .ws-cmp-rank.r1 {{ background: linear-gradient(135deg,#FFD66B,#F9A825); }}
        .ws-cmp-rank.r2 {{ background: linear-gradient(135deg,#D7DCE6,#9AA3B5); }}
        .ws-cmp-rank.r3 {{ background: linear-gradient(135deg,#E2A772,#B97A45); }}
        .ws-cmp-level {{
            font-size:.62rem; font-weight:800; letter-spacing:.08em; text-transform:uppercase;
            padding:3px 9px; border-radius:999px;
            background: rgba(255,255,255,0.05);
        }}
        .ws-cmp-card-name {{ font-size:1.02rem; font-weight:800; color:#F2F4FA; line-height:1.2;
            white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
        .ws-cmp-card-score {{ display:flex; align-items:baseline; gap:6px; margin:8px 0 2px; }}
        .ws-cmp-card-score b {{ font-size:2rem; font-weight:800; line-height:1; }}
        .ws-cmp-card-score span {{ font-size:.72rem; color:{MUTED}; }}
        .ws-cmp-bar-track {{ background: rgba(255,255,255,0.06); height:6px; border-radius:999px; overflow:hidden; margin:6px 0 10px; }}
        .ws-cmp-bar-fill {{ height:100%; border-radius:999px; transition: width .8s ease; }}
        .ws-cmp-mini {{ display:flex; gap:6px; }}
        .ws-cmp-mini-cell {{ flex:1; background: rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.05);
            border-radius:9px; padding:6px 4px; text-align:center; }}
        .ws-cmp-mini-val {{ font-size:.92rem; font-weight:800; color:#E6E9F2; font-variant-numeric:tabular-nums; }}
        .ws-cmp-mini-lbl {{ font-size:.58rem; letter-spacing:.06em; text-transform:uppercase; color:{MUTED}; margin-top:2px; }}
        .ws-cmp-card-head {{ font-size:.74rem; color:#AAB2C5; margin-top:8px; line-height:1.35; }}

        .ws-cmp-matrix {{ display:grid; gap:5px; margin-top:4px; }}
        .ws-cmp-mcorner {{ font-size:.66rem; letter-spacing:.1em; text-transform:uppercase; color:{MUTED};
            font-weight:700; display:flex; align-items:flex-end; padding:0 4px 6px; }}
        .ws-cmp-mhead {{ text-align:center; font-size:.78rem; font-weight:800; color:#E6E9F2;
            padding:6px 4px; border-bottom:2px solid rgba(255,255,255,0.08);
            white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
        .ws-cmp-mhead.is-winner {{ color: var(--hue, {PRIMARY}); border-bottom-color: var(--hue, {PRIMARY}); }}
        .ws-cmp-mlabel {{ font-size:.78rem; color:#AAB2C5; font-weight:600; display:flex; align-items:center; padding:0 4px; }}
        .ws-cmp-cell {{ text-align:center; border-radius:8px; padding:8px 4px;
            font-weight:800; font-size:.9rem; font-variant-numeric:tabular-nums; }}
        .ws-cmp-cell.head-row {{ font-size:1.05rem; }}

        /* ---------- StaySafe — accommodation safety picker ---------- */
        .ws-stay-hero {{
            position:relative; overflow:hidden;
            display:flex; gap:24px; align-items:center;
            background:{CARD}; border:1px solid rgba(255,255,255,0.06);
            border-left:6px solid var(--hue, {PRIMARY});
            border-radius:16px; padding:20px 24px; margin-bottom:14px;
        }}
        .ws-stay-hero::before {{
            content:""; position:absolute; inset:0;
            background: radial-gradient(120% 160% at 0% 0%, var(--glow, transparent) 0%, transparent 55%);
            pointer-events:none;
        }}
        .ws-stay-hero-body {{ position:relative; flex:1; min-width:0; }}
        .ws-stay-crown {{
            display:inline-flex; align-items:center; gap:6px;
            font-size:.72rem; font-weight:800; letter-spacing:.12em; text-transform:uppercase;
            color: var(--hue, {PRIMARY});
            background: rgba(255,255,255,0.04); border:1px solid var(--hue, {PRIMARY});
            border-radius:999px; padding:4px 12px; margin-bottom:8px;
        }}
        .ws-stay-hero-title {{ font-size:1.5rem; font-weight:800; line-height:1.25; color:#F2F4FA; }}
        .ws-stay-hero-title strong {{ color: var(--hue, {PRIMARY}); }}
        .ws-stay-hero-detail {{ font-size:.95rem; color:#C7CEDE; margin-top:6px; }}
        .ws-stay-hero-detail strong {{ color: var(--hue, {PRIMARY}); }}
        .ws-stay-hero-meta {{ font-size:.78rem; color:{MUTED}; margin-top:10px; }}
        .ws-stay-chip {{
            display:inline-block; font-size:.66rem; font-weight:700; letter-spacing:.06em;
            text-transform:uppercase; padding:2px 8px; border-radius:999px;
            background: rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.08);
            color:#C7CEDE; margin-right:6px;
        }}
        .ws-stay-chip.profile {{ color: var(--hue, {PRIMARY}); border-color: var(--hue, {PRIMARY}); }}
        .ws-stay-margin {{
            position:relative; text-align:center; flex-shrink:0;
            background: rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.08);
            border-radius:14px; padding:12px 18px; min-width:96px;
        }}
        .ws-stay-margin-val {{ font-size:2rem; font-weight:800; color: var(--hue, {PRIMARY}); line-height:1; }}
        .ws-stay-margin-lbl {{ font-size:.62rem; letter-spacing:.12em; text-transform:uppercase; color:{MUTED}; margin-top:4px; font-weight:700; }}

        .ws-stay-podium {{
            display:grid; gap:12px; margin-bottom:14px;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        }}
        .ws-stay-card {{
            background:{CARD}; border:1px solid rgba(255,255,255,0.06);
            border-radius:14px; padding:14px 16px; position:relative; overflow:hidden;
        }}
        .ws-stay-card.is-winner {{
            border-color: var(--hue, {PRIMARY});
            box-shadow: 0 0 0 1px var(--hue, {PRIMARY}), 0 10px 30px -12px var(--hue, {PRIMARY});
        }}
        .ws-stay-card-top {{
            display:flex; align-items:center; justify-content:space-between; margin-bottom:8px;
        }}
        .ws-stay-rank {{
            width:26px; height:26px; border-radius:8px; flex-shrink:0;
            display:flex; align-items:center; justify-content:center;
            font-weight:800; font-size:.82rem; color:#0E1117;
            background: rgba(255,255,255,0.16);
        }}
        .ws-stay-rank.r1 {{ background: linear-gradient(135deg,#FFD66B,#F9A825); }}
        .ws-stay-rank.r2 {{ background: linear-gradient(135deg,#D7DCE6,#9AA3B5); }}
        .ws-stay-rank.r3 {{ background: linear-gradient(135deg,#E2A772,#B97A45); }}
        .ws-stay-kind {{
            font-size:.6rem; font-weight:800; letter-spacing:.1em; text-transform:uppercase;
            padding:2px 8px; border-radius:999px;
            background: rgba(255,255,255,0.05); color:#C7CEDE;
            border:1px solid rgba(255,255,255,0.08);
        }}
        .ws-stay-level {{
            font-size:.62rem; font-weight:800; letter-spacing:.08em; text-transform:uppercase;
            padding:3px 9px; border-radius:999px; background: rgba(255,255,255,0.05);
        }}
        .ws-stay-card-name {{
            font-size:1.02rem; font-weight:800; color:#F2F4FA; line-height:1.2;
            white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
        }}
        .ws-stay-card-score {{ display:flex; align-items:baseline; gap:6px; margin:8px 0 2px; }}
        .ws-stay-card-score b {{ font-size:2rem; font-weight:800; line-height:1; }}
        .ws-stay-card-score span {{ font-size:.72rem; color:{MUTED}; }}
        .ws-stay-bar-track {{
            background: rgba(255,255,255,0.06); height:6px; border-radius:999px;
            overflow:hidden; margin:6px 0 10px;
        }}
        .ws-stay-bar-fill {{ height:100%; border-radius:999px; transition: width .8s ease; }}
        .ws-stay-tri {{ display:flex; gap:6px; margin-top:4px; }}
        .ws-stay-tri-cell {{
            flex:1; background: rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.05);
            border-radius:9px; padding:6px 4px; text-align:center;
        }}
        .ws-stay-tri-val {{
            font-size:.92rem; font-weight:800; color:#E6E9F2; font-variant-numeric:tabular-nums;
        }}
        .ws-stay-tri-lbl {{
            font-size:.58rem; letter-spacing:.06em; text-transform:uppercase; color:{MUTED}; margin-top:2px;
        }}
        .ws-stay-card-head {{ font-size:.74rem; color:#AAB2C5; margin-top:8px; line-height:1.35; }}
        .ws-stay-why {{
            font-size:.72rem; color:#9CA3B8; margin-top:6px;
            border-top: 1px dashed rgba(255,255,255,0.06); padding-top:8px;
        }}

        /* 24-hour risk sparkline (per stay card + per matrix row) */
        .ws-stay-spark {{
            display:flex; gap:1px; align-items:flex-end; height:32px; margin-top:8px;
            background: rgba(255,255,255,0.02); border-radius:6px; padding:3px 4px 2px;
        }}
        .ws-stay-spark-bar {{
            flex:1; min-width:0; border-radius:2px 2px 0 0; opacity:.95;
            transition: opacity .15s ease;
        }}
        .ws-stay-spark-bar:hover {{ opacity:1; }}
        .ws-stay-spark-axis {{
            display:flex; justify-content:space-between; font-size:.55rem; color:{MUTED};
            letter-spacing:.06em; margin-top:2px; padding: 0 4px;
        }}

        /* Help-leg breakdown — 3 columns with walk time */
        .ws-stay-legs {{
            display:grid; gap:8px; grid-template-columns: repeat(3, 1fr); margin-top:10px;
        }}
        .ws-stay-leg {{
            background: rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.06);
            border-radius:10px; padding:8px 10px; min-width:0;
        }}
        .ws-stay-leg-cat {{
            font-size:.58rem; font-weight:800; letter-spacing:.1em; text-transform:uppercase;
            color: var(--hue, #C7CEDE); margin-bottom:2px;
        }}
        .ws-stay-leg-name {{
            font-size:.78rem; font-weight:700; color:#E6E9F2;
            white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
        }}
        .ws-stay-leg-meta {{
            font-size:.7rem; color:{MUTED}; margin-top:2px; font-variant-numeric:tabular-nums;
        }}
        .ws-stay-leg-bar {{
            background: rgba(255,255,255,0.05); height:4px; border-radius:999px; margin-top:6px; overflow:hidden;
        }}
        .ws-stay-leg-bar-fill {{ height:100%; border-radius:999px; }}

        /* Matrix (reuses ws-cmp-* patterns but namespaced for tuning) */
        .ws-stay-matrix {{ display:grid; gap:5px; margin-top:6px; }}
        .ws-stay-mcorner {{
            font-size:.66rem; letter-spacing:.1em; text-transform:uppercase; color:{MUTED};
            font-weight:700; display:flex; align-items:flex-end; padding:0 4px 6px;
        }}
        .ws-stay-mhead {{
            text-align:center; font-size:.78rem; font-weight:800; color:#E6E9F2;
            padding:6px 4px; border-bottom:2px solid rgba(255,255,255,0.08);
            white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
        }}
        .ws-stay-mhead.is-winner {{
            color: var(--hue, {PRIMARY}); border-bottom-color: var(--hue, {PRIMARY});
        }}
        .ws-stay-mlabel {{
            font-size:.78rem; color:#AAB2C5; font-weight:600;
            display:flex; align-items:center; padding:0 4px;
        }}
        .ws-stay-mlabel-w {{
            font-size:.58rem; color:{MUTED}; margin-left:6px;
            background: rgba(255,255,255,0.04); padding:1px 6px; border-radius:999px;
        }}
        .ws-stay-cell {{
            text-align:center; border-radius:8px; padding:8px 4px;
            font-weight:800; font-size:.86rem; font-variant-numeric:tabular-nums;
            line-height:1.2;
        }}
        .ws-stay-cell.head-row {{ font-size:1.05rem; }}
        .ws-stay-cell-sub {{
            display:block; font-size:.55rem; font-weight:600;
            letter-spacing:.04em; color:#AAB2C5; margin-top:2px;
            text-transform:none;
        }}

        /* -------------------------------------------------- Refuge */
        .ws-ref-hero {{
            background: linear-gradient(135deg, var(--glow, rgba(239,68,68,0.20)) 0%, {CARD} 60%);
            border: 1px solid var(--hue, #EF4444);
            border-left-width: 4px;
            border-radius: 18px;
            padding: 22px 26px;
            display: grid;
            grid-template-columns: 168px 1fr auto;
            gap: 26px;
            align-items: center;
            margin-bottom: 18px;
            box-shadow: 0 12px 28px var(--glow, rgba(239,68,68,0.2));
        }}
        .ws-ref-hero-body {{ min-width: 0; }}
        .ws-ref-pill {{
            display:inline-block; padding:3px 12px; border-radius:999px;
            font-size:.66rem; font-weight:800; letter-spacing:.12em;
            text-transform: uppercase;
            background: rgba(255,255,255,0.06);
            color: var(--hue, #EF4444);
            border: 1px solid var(--hue, #EF4444);
            margin-bottom:.55rem;
        }}
        .ws-ref-hero-title {{
            font-size: 1.45rem; font-weight: 800; line-height: 1.15;
            letter-spacing: -0.02em; color: #F2F4FA; margin-bottom: 4px;
        }}
        .ws-ref-hero-detail {{ font-size:.92rem; color:#C9D0E0; line-height:1.45; }}
        .ws-ref-hero-meta {{
            display:flex; flex-wrap:wrap; gap:8px; margin-top:.9rem;
            font-size:.72rem; color:{MUTED};
        }}
        .ws-ref-chip {{
            padding:3px 10px; border-radius:999px; background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.08);
        }}
        .ws-ref-chip.warn {{
            color: var(--hue, #EF4444);
            border-color: var(--hue, #EF4444);
            background: rgba(239,68,68,0.08);
        }}
        .ws-ref-compass {{
            width: 168px; height: 168px; border-radius: 50%;
            background: conic-gradient(var(--hue, #EF4444) calc(var(--pct, 100) * 1%), rgba(255,255,255,0.07) 0);
            display:flex; align-items:center; justify-content:center;
            position: relative; flex-shrink: 0;
        }}
        .ws-ref-compass::after {{
            content:""; position:absolute; inset:10px;
            background: {CARD}; border-radius: 50%;
        }}
        .ws-ref-compass-inner {{
            position:relative; z-index:1; text-align:center;
        }}
        .ws-ref-compass-arrow {{
            font-size: 2.7rem; line-height:1;
            transform: rotate(var(--bearing, 0deg));
            display:inline-block; transform-origin: 50% 55%;
            color: var(--hue, #EF4444);
            text-shadow: 0 2px 6px var(--glow, rgba(239,68,68,0.4));
        }}
        .ws-ref-compass-label {{
            display:block; font-size:.95rem; font-weight:800;
            letter-spacing:.18em; color: var(--hue, #EF4444); margin-top:6px;
        }}
        .ws-ref-compass-sub {{
            display:block; font-size:.62rem; color:{MUTED}; margin-top:3px;
            letter-spacing:.08em;
        }}
        .ws-ref-here {{
            text-align:right; padding-left: 12px;
            border-left: 1px solid rgba(255,255,255,0.08);
        }}
        .ws-ref-here-val {{
            font-size: 1.85rem; font-weight: 800; line-height:1;
            font-variant-numeric: tabular-nums;
        }}
        .ws-ref-here-lbl {{
            font-size: .58rem; letter-spacing:.16em; text-transform: uppercase;
            color:{MUTED}; margin-top:4px; font-weight: 700;
        }}

        /* Podium grid */
        .ws-ref-podium {{
            display:grid; grid-template-columns: repeat(auto-fit, minmax(245px, 1fr));
            gap: 10px; margin: 8px 0 16px;
        }}
        .ws-ref-card {{
            background: {CARD};
            border: 1px solid rgba(255,255,255,0.07);
            border-left: 4px solid var(--hue, #EF4444);
            border-radius: 14px;
            padding: 14px 16px;
        }}
        .ws-ref-card.is-top {{
            background: linear-gradient(135deg, rgba(255,255,255,0.04) 0%, {CARD} 60%);
            border-color: var(--hue, #EF4444);
            box-shadow: 0 8px 20px var(--glow, rgba(239,68,68,0.18));
        }}
        .ws-ref-card-top {{
            display:flex; align-items:center; justify-content:space-between;
            margin-bottom: 8px;
        }}
        .ws-ref-rank {{
            font-size:.7rem; font-weight:800; color:#E6E9F2;
            background: rgba(255,255,255,0.06); border-radius:999px;
            padding: 3px 10px; letter-spacing:.06em;
        }}
        .ws-ref-rank.r1 {{ background: rgba(255,191,60,0.2); color:#FFD66B; }}
        .ws-ref-band {{
            font-size:.65rem; font-weight:800; letter-spacing:.10em;
            text-transform: uppercase;
            padding: 3px 9px; border-radius:999px;
        }}
        .ws-ref-tier {{
            font-size:.7rem; color:#AAB2C5; display:flex; align-items:center; gap:6px;
            margin-bottom: 6px;
        }}
        .ws-ref-card-name {{
            font-size:1.02rem; font-weight:800; color:#F2F4FA;
            line-height:1.2; margin-bottom: 6px;
        }}
        .ws-ref-card-score {{
            display:flex; align-items:baseline; gap:6px; margin: 4px 0 2px;
        }}
        .ws-ref-card-score b {{ font-size:2rem; font-weight:800; line-height:1; }}
        .ws-ref-card-score span {{ font-size:.7rem; color:{MUTED}; }}
        .ws-ref-bar-track {{
            background: rgba(255,255,255,0.05); height:5px; border-radius:999px;
            overflow:hidden; margin: 6px 0 10px;
        }}
        .ws-ref-bar-fill {{ height:100%; border-radius:999px; }}
        .ws-ref-mini {{
            display:grid; grid-template-columns: repeat(3, 1fr); gap:6px;
            margin-top:6px;
        }}
        .ws-ref-mini-cell {{
            background: rgba(255,255,255,0.03); border-radius:8px;
            padding:6px 4px; text-align:center;
        }}
        .ws-ref-mini-val {{
            font-size:.92rem; font-weight:800; color:#E6E9F2;
            font-variant-numeric: tabular-nums;
        }}
        .ws-ref-mini-lbl {{
            font-size:.55rem; color:{MUTED}; letter-spacing:.08em;
            text-transform: uppercase; margin-top:2px;
        }}
        .ws-ref-script {{
            margin-top: 10px;
            padding: 9px 11px;
            background: rgba(255,255,255,0.03);
            border-left: 2px solid var(--hue, #EF4444);
            border-radius: 6px;
            font-size: .76rem; color: #D2D7E5; line-height: 1.4;
        }}
        .ws-ref-notes {{
            margin-top:8px; font-size:.72rem; color:#AAB2C5; line-height:1.4;
        }}
        .ws-ref-notes li {{ margin-left: 16px; }}

        /* Matrix (heat row) */
        .ws-ref-matrix {{ display:grid; gap:5px; margin-top:10px; }}
        .ws-ref-mcorner {{
            font-size:.66rem; letter-spacing:.1em; text-transform:uppercase; color:{MUTED};
            font-weight:700; display:flex; align-items:flex-end; padding:0 4px 6px;
        }}
        .ws-ref-mhead {{
            text-align:center; font-size:.74rem; font-weight:800; color:#E6E9F2;
            padding:6px 4px; border-bottom:2px solid rgba(255,255,255,0.08);
            white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
        }}
        .ws-ref-mhead.is-top {{
            color: var(--hue, {PRIMARY}); border-bottom-color: var(--hue, {PRIMARY});
        }}
        .ws-ref-mlabel {{
            font-size:.78rem; color:#AAB2C5; font-weight:600;
            display:flex; align-items:center; padding:0 4px;
        }}
        .ws-ref-mlabel-w {{
            font-size:.58rem; color:{MUTED}; margin-left:6px;
            background: rgba(255,255,255,0.04); padding:1px 6px; border-radius:999px;
        }}
        .ws-ref-cell {{
            text-align:center; border-radius:8px; padding:8px 4px;
            font-weight:800; font-size:.84rem; font-variant-numeric:tabular-nums;
            line-height:1.2;
        }}
        .ws-ref-cell.head-row {{ font-size:1.05rem; }}

        /* Corridor strip — visualises path_safety along the 5 waypoints */
        .ws-ref-corridor {{
            display:flex; gap:3px; margin-top: 8px;
        }}
        .ws-ref-corridor-step {{
            flex: 1; height: 10px; border-radius:3px;
            background: var(--step-hue, #444);
            opacity:.92;
        }}
        .ws-ref-corridor-step.fenced {{
            outline: 1.5px dashed rgba(239,68,68,0.85); outline-offset:-1px;
        }}

        /* Emergency card */
        .ws-ref-emergency {{
            background: linear-gradient(135deg, rgba(239,68,68,0.06) 0%, {CARD} 70%);
            border: 1px solid rgba(239,68,68,0.32);
            border-radius: 14px;
            padding: 16px 18px;
            margin-top: 14px;
        }}
        .ws-ref-emergency-head {{
            display:flex; align-items:center; gap:10px; margin-bottom:10px;
        }}
        .ws-ref-emergency-flag {{ font-size: 1.55rem; }}
        .ws-ref-emergency-title {{
            font-size: 1rem; font-weight: 800; color:#F2F4FA;
            letter-spacing:-0.01em;
        }}
        .ws-ref-emergency-grid {{
            display:grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap:8px;
        }}
        .ws-ref-emergency-cell {{
            background: rgba(0,0,0,0.18);
            border: 1px solid rgba(239,68,68,0.18);
            border-radius:10px;
            padding: 10px 12px;
        }}
        .ws-ref-emergency-num {{
            font-size: 1.4rem; font-weight: 800; color: #FF6A6A;
            font-variant-numeric: tabular-nums; letter-spacing: .01em;
        }}
        .ws-ref-emergency-lbl {{
            font-size: .62rem; letter-spacing:.12em; text-transform: uppercase;
            color:{MUTED}; font-weight:700; margin-top: 4px;
        }}
        .ws-ref-emergency-note {{
            font-size:.72rem; color:#AAB2C5; margin-top: 10px;
        }}

        /* Beacon block */
        .ws-ref-beacon {{
            background: rgba(255,191,60,0.06);
            border: 1px dashed rgba(255,191,60,0.45);
            border-radius: 12px;
            padding: 12px 14px;
            margin-top: 12px;
        }}
        .ws-ref-beacon-title {{
            font-size:.66rem; font-weight:800; letter-spacing:.15em;
            text-transform: uppercase; color:#FFD66B; margin-bottom:6px;
        }}
        .ws-ref-beacon-body {{
            font-family: 'JetBrains Mono','SF Mono', ui-monospace, monospace;
            font-size:.74rem; color:#E6E9F2; line-height:1.45;
            white-space: pre-wrap; word-break: break-word;
        }}

        /* Fallback / empty */
        .ws-ref-empty {{
            background: {CARD};
            border: 1px dashed rgba(255,255,255,0.12);
            border-radius: 14px; padding: 22px 24px;
            color:#AAB2C5; font-size:.88rem; line-height:1.45;
        }}
        .ws-ref-empty-title {{
            font-size:1.05rem; font-weight:800; color:#F2F4FA;
            margin-bottom: 6px; letter-spacing:-0.01em;
        }}
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


# ===================== Itinerary (Day 21) =====================

def _safety_color(score: int) -> str:
    if score >= 80: return "#53E3A6"
    if score >= 60: return "#7EE7DA"
    if score >= 35: return "#F9C440"
    if score >= 20: return "#FF7F50"
    return "#FF3D60"


def _safety_band(score: int) -> str:
    if score >= 80: return "Safe"
    if score >= 60: return "Mostly Safe"
    if score >= 35: return "Caution"
    if score >= 20: return "High Risk"
    return "Danger"


def _fmt_dt(dt) -> str:
    return dt.strftime("%a %H:%M") if dt is not None else "—"


def _fmt_hm(dt) -> str:
    return dt.strftime("%H:%M") if dt is not None else "—"


def _fmt_duration(minutes: float) -> str:
    if minutes is None:
        return "—"
    m = int(round(minutes))
    if m < 60:
        return f"{m} min"
    h, rem = divmod(m, 60)
    return f"{h}h{rem:02d}" if rem else f"{h}h"


def render_itinerary_empty(
    *, hint: str = "Add at least 2 stops, set a depart time, and click **Plan itinerary** to chain them into one safety-aware schedule.",
) -> None:
    st.markdown(
        f"""
        <div class='ws-itin-empty'>
          <div class='ws-itin-empty-icon'>🗺️</div>
          <h4>No itinerary yet</h4>
          <p>{hint}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_itinerary_summary(plan) -> None:
    score = plan.composite_score
    color = _safety_color(score)
    band = _safety_band(score)
    n_stops = len(plan.stops)
    legs = plan.legs

    bands = ""
    if legs:
        # mini "legs by safety band" stripe — counts per band
        buckets = {"Safe": 0, "Mostly Safe": 0, "Caution": 0, "High Risk": 0, "Danger": 0}
        for l in legs:
            buckets[_safety_band(l.avg_safety)] += 1
        rows = "".join(
            f"<div class='ws-itin-hero-band'>"
            f"<span class='ws-itin-hero-band-dot' style='background:{_safety_color({'Safe':90,'Mostly Safe':70,'Caution':50,'High Risk':25,'Danger':10}[b])};'></span>"
            f"{b} · {n}</div>"
            for b, n in buckets.items() if n
        )
        bands = f"<div class='ws-itin-hero-bands'>{rows}</div>"

    mode_label = {"safest": "Safest", "fastest": "Fastest", "forecast-safest": "Forecast-aware"}.get(plan.mode, plan.mode)

    st.markdown(
        f"""
        <div class='ws-itin-hero'>
          <div class='ws-itin-hero-ring' style='--ring:{color}; --pct:{score};'>
            <div class='ws-itin-hero-ring-inner'>
              <div class='ws-itin-hero-ring-val' style='color:{color};'>{score}</div>
              <div class='ws-itin-hero-ring-lbl'>Itinerary score</div>
            </div>
          </div>
          <div>
            <div class='ws-itin-hero-title'>{n_stops} stops · {plan.total_km:g} km · {_fmt_duration(plan.total_minutes)}</div>
            <div class='ws-itin-hero-sub'>{mode_label} · departs {_fmt_dt(plan.depart_at)} · arrives {_fmt_hm(plan.arrive_at)} · {band} corridor</div>
            <div class='ws-itin-hero-stats'>
              <div class='ws-itin-hero-stat'>
                <div class='ws-itin-hero-stat-lbl'>Travel</div>
                <div class='ws-itin-hero-stat-val'>{_fmt_duration(plan.total_travel_min)}</div>
              </div>
              <div class='ws-itin-hero-stat'>
                <div class='ws-itin-hero-stat-lbl'>Dwell</div>
                <div class='ws-itin-hero-stat-val'>{_fmt_duration(plan.total_dwell_min)}</div>
              </div>
              <div class='ws-itin-hero-stat'>
                <div class='ws-itin-hero-stat-lbl'>Avg safety</div>
                <div class='ws-itin-hero-stat-val'>{plan.avg_safety}<small>/100</small></div>
              </div>
              <div class='ws-itin-hero-stat'>
                <div class='ws-itin-hero-stat-lbl'>Min safety</div>
                <div class='ws-itin-hero-stat-val'>{plan.min_safety}<small>/100</small></div>
              </div>
              <div class='ws-itin-hero-stat'>
                <div class='ws-itin-hero-stat-lbl'>Risk km</div>
                <div class='ws-itin-hero-stat-val'>{plan.danger_km:g}</div>
              </div>
            </div>
          </div>
          {bands}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_itinerary_timeline(plan) -> None:
    """Gantt-style horizontal timeline: travel bars coloured by safety,
    dwell bars hatched teal between them."""
    if not plan.legs:
        return
    from datetime import timedelta as _td

    t0 = plan.depart_at
    t1 = plan.arrive_at
    span_min = max(15.0, (t1 - t0).total_seconds() / 60.0)

    def _pct(dt) -> float:
        return max(0.0, min(100.0, ((dt - t0).total_seconds() / 60.0) / span_min * 100.0))

    # Ticks: pick ~6 evenly spaced ticks (rounded to the nearest 15 / 30 / 60 min).
    if span_min <= 60: step = 10
    elif span_min <= 180: step = 30
    elif span_min <= 360: step = 60
    else: step = 120
    ticks_html_parts = []
    cur = t0
    while cur <= t1:
        ticks_html_parts.append(
            f"<div class='ws-itin-gantt-tick' style='left:{_pct(cur):.2f}%;'>{cur.strftime('%H:%M')}</div>"
        )
        cur = cur + _td(minutes=step)
    ticks_html = "".join(ticks_html_parts)

    rows_html_parts = []
    for i, leg in enumerate(plan.legs, start=1):
        left = _pct(leg.depart_at)
        right = _pct(leg.arrive_at)
        width = max(0.5, right - left)
        bar_color = _safety_color(leg.avg_safety)
        bar_label = (
            f"{i}. {leg.from_stop.name} → {leg.to_stop.name} · "
            f"{leg.distance_km:g} km · {_fmt_duration(leg.eta_minutes)} · {leg.avg_safety}/100"
        )
        row_inner = (
            f"<div class='ws-itin-gantt-bar' style='left:{left:.2f}%; width:{width:.2f}%; "
            f"background: linear-gradient(135deg, {bar_color} 0%, rgba(255,255,255,0.08) 110%); "
            f"color: rgba(14,17,23,0.92);' title='{bar_label}'>"
            f"{leg.distance_km:g} km · {leg.avg_safety}"
            f"</div>"
        )
        # dwell block after each leg (except the last)
        dwell_inner = ""
        if i < len(plan.legs) and leg.to_stop.dwell_min > 0:
            dwell_start = leg.arrive_at
            dwell_end = dwell_start + _td(minutes=leg.to_stop.dwell_min)
            dl = _pct(dwell_start)
            dr = _pct(dwell_end)
            dw = max(0.5, dr - dl)
            dwell_inner = (
                f"<div class='ws-itin-gantt-bar dwell' style='left:{dl:.2f}%; width:{dw:.2f}%;' "
                f"title='Dwell at {leg.to_stop.name} · {leg.to_stop.dwell_min} min'>"
                f"⏱ {leg.to_stop.dwell_min}m"
                f"</div>"
            )
        rows_html_parts.append(
            f"<div class='ws-itin-gantt-row'>"
            f"<div class='ws-itin-gantt-row-lbl'>{i}. {leg.from_stop.name} → {leg.to_stop.name}</div>"
            f"{row_inner}{dwell_inner}"
            f"</div>"
        )
    rows_html = "".join(rows_html_parts)

    st.markdown(
        f"""
        <div class='ws-itin-gantt'>
          <div class='ws-itin-gantt-hdr'>
            <h4>Day timeline</h4>
            <div class='ws-itin-gantt-span'>{_fmt_dt(t0)} → {_fmt_hm(t1)} · {_fmt_duration(plan.total_minutes)}</div>
          </div>
          <div class='ws-itin-gantt-ruler'>{ticks_html}</div>
          {rows_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_itinerary_legs(plan) -> None:
    if not plan.legs:
        return
    for i, leg in enumerate(plan.legs, start=1):
        color = _safety_color(leg.avg_safety)
        band = _safety_band(leg.avg_safety)
        pct_fill = max(2, min(100, leg.avg_safety))
        notes = " · ".join(leg.route.notes[:2]) if leg.route.notes else ""
        notes_html = (
            f"<div style='font-size:.7rem; color:{MUTED}; margin-top:8px;'>{notes}</div>"
            if notes else ""
        )
        st.markdown(
            f"""
            <div class='ws-itin-leg' style='--accent:{color};'>
              <div class='ws-itin-leg-hdr'>
                <div class='ws-itin-leg-title'>{i}. {leg.from_stop.name} → {leg.to_stop.name}</div>
                <div class='ws-itin-leg-time'>{_fmt_hm(leg.depart_at)} → {_fmt_hm(leg.arrive_at)}</div>
              </div>
              <div class='ws-itin-leg-bar-track'>
                <div class='ws-itin-leg-bar-fill' style='width:{pct_fill}%;'></div>
              </div>
              <div class='ws-itin-leg-stats'>
                <div class='ws-itin-leg-stat'>
                  <div class='ws-itin-leg-stat-lbl'>Distance</div>
                  <div class='ws-itin-leg-stat-val'>{leg.distance_km:g} <small>km</small></div>
                </div>
                <div class='ws-itin-leg-stat'>
                  <div class='ws-itin-leg-stat-lbl'>ETA</div>
                  <div class='ws-itin-leg-stat-val'>{_fmt_duration(leg.eta_minutes)}</div>
                </div>
                <div class='ws-itin-leg-stat'>
                  <div class='ws-itin-leg-stat-lbl'>Avg safety</div>
                  <div class='ws-itin-leg-stat-val' style='color:{color};'>{leg.avg_safety}</div>
                </div>
                <div class='ws-itin-leg-stat'>
                  <div class='ws-itin-leg-stat-lbl'>Min safety</div>
                  <div class='ws-itin-leg-stat-val'>{leg.min_safety}</div>
                </div>
              </div>
              <div style='margin-top:8px;'>
                <span class='ws-itin-leg-safety' style='background:{color}22; color:{color}; border:1px solid {color}55;'>
                  ● {band}
                </span>
                {('<span class="ws-mini-pill" style="margin-left:4px;">Risky · ' + f'{leg.danger_km:g} km</span>') if leg.danger_km > 0 else ''}
              </div>
              {notes_html}
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_itinerary_windows(windows, baseline_time, *, top_k: int = 5) -> None:
    """Show the top-k start-window candidates as score bars vs the current pick."""
    if not windows:
        return
    top = windows[:top_k]
    best_score = max(1, top[0][1].composite_score)
    rows = []
    for t, plan in top:
        delta_min = int(round((t - baseline_time).total_seconds() / 60))
        sign = "" if delta_min == 0 else ("+" if delta_min > 0 else "")
        delta_lbl = "your pick" if delta_min == 0 else f"{sign}{delta_min} min"
        width = max(4, int(plan.composite_score * 100 / best_score))
        accent = _safety_color(plan.composite_score)
        rows.append(
            f"<div class='ws-itin-window-row'>"
            f"<div class='ws-itin-window-time'>{t.strftime('%a %H:%M')}</div>"
            f"<div class='ws-itin-window-delta'>{delta_lbl}</div>"
            f"<div class='ws-itin-window-bar'><div class='ws-itin-window-fill' "
            f"style='width:{width}%; --accent:{accent};'></div></div>"
            f"<div class='ws-itin-window-score' style='color:{accent};'>{plan.composite_score}</div>"
            f"</div>"
        )
    st.markdown("".join(rows), unsafe_allow_html=True)


# ===== Sentinel =====

def _sentinel_status_hue(status: str) -> str:
    return {
        "Critical": "#FF3D60",
        "Active":   "#FF7F50",
        "Watch":    "#F9C440",
        "Calm":     "#53E3A6",
    }.get(status, MUTED)


def _cluster_status_hue(status: str) -> str:
    return {
        "Critical": "#FF3D60",
        "Emerging": "#FF7F50",
        "Steady":   "#F9C440",
        "Cooling":  "#53E3A6",
    }.get(status, MUTED)


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha:.3f})"


def render_sentinel_pulse(pulse) -> None:
    """Hero card for the global Risk Pulse — status badge, headline, counters."""
    hue = _sentinel_status_hue(pulse.status)
    glow = _hex_to_rgba(hue, 0.22)

    counter_specs = [
        ("Critical", pulse.n_critical, "#FF3D60"),
        ("Emerging", pulse.n_emerging, "#FF7F50"),
        ("Steady",   pulse.n_steady,   "#F9C440"),
        ("Cooling",  pulse.n_cooling,  "#53E3A6"),
    ]
    chips = "".join(
        f"<div class='ws-sent-chip'>"
        f"<span class='ws-sent-chip-dot' style='background:{c};'></span>"
        f"{lbl} · <span style='font-variant-numeric:tabular-nums;'>{n}</span>"
        f"</div>"
        for lbl, n, c in counter_specs
    )

    dom = ""
    if pulse.dominant_category:
        from sentinel import CATEGORY_ICON  # local import to avoid cycle on theme-only callers
        ic = CATEGORY_ICON.get(pulse.dominant_category, "")
        dom = f"{ic} {pulse.dominant_category}"

    st.markdown(
        f"""
        <div class="ws-sent-hero" style="--pulse-hue:{hue}; --pulse-glow:{glow};">
          <div class="ws-sent-hero-glow"></div>
          <div class="ws-sent-hero-inner">
            <div class="ws-sent-pulse-dot">
              <div class="ws-sent-pulse-core"></div>
            </div>
            <div class="ws-sent-status-block">
              <div class="ws-sent-status-kicker">Risk Pulse</div>
              <div class="ws-sent-status-label">{pulse.status}</div>
              <div class="ws-sent-headline">{pulse.headline}</div>
            </div>
            <div class="ws-sent-stats">
              <div class="ws-sent-stat">
                <div class="ws-sent-stat-val">{pulse.n_clusters}</div>
                <div class="ws-sent-stat-lbl">Clusters</div>
              </div>
              <div class="ws-sent-stat">
                <div class="ws-sent-stat-val">{pulse.recent_window_count}</div>
                <div class="ws-sent-stat-lbl">Last {pulse.recent_days}d</div>
              </div>
              <div class="ws-sent-stat">
                <div class="ws-sent-stat-val">{pulse.baseline_window_count}</div>
                <div class="ws-sent-stat-lbl">Prior {pulse.baseline_days}d</div>
              </div>
              <div class="ws-sent-stat">
                <div class="ws-sent-stat-val">{pulse.velocity:.2f}×</div>
                <div class="ws-sent-stat-lbl">Velocity</div>
              </div>
            </div>
          </div>
          <div class="ws-sent-counters">{chips}{('<div class=ws-sent-chip>Mostly · ' + dom + '</div>') if dom else ''}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sentinel_watch_banner(pulse) -> None:
    """One-line banner used on the Map tab to surface emerging hotspots globally."""
    if pulse.status == "Calm":
        return
    hue = _sentinel_status_hue(pulse.status)
    bg = _hex_to_rgba(hue, 0.14)
    bd = _hex_to_rgba(hue, 0.30)
    icon = {"Critical": "🚨", "Active": "⚠️", "Watch": "👀", "Calm": "✅"}.get(pulse.status, "👀")
    if pulse.status == "Critical":
        msg = f"Sentinel: <strong>CRITICAL</strong> — {pulse.n_critical} hotspot(s) erupting now."
    elif pulse.status == "Active":
        msg = f"Sentinel: <strong>ACTIVE</strong> — {pulse.n_emerging} emerging hotspot(s)."
    else:
        msg = f"Sentinel: <strong>WATCH</strong> — {pulse.headline}."
    st.markdown(
        f"""
        <div class="ws-sent-banner" style="--banner-hue:{hue}; --banner-bg:{bg}; --banner-bd:{bd};">
          <div class="ws-sent-banner-icon">{icon}</div>
          <div class="ws-sent-banner-text">{msg}<small>open the <em>Sentinel</em> tab for cluster intel</small></div>
          <div class="ws-sent-banner-meta">{pulse.recent_window_count} incidents · {pulse.recent_days} d window</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sentinel_empty(*, hint: str = "No incident clusters at the current ε / min-samples threshold. Loosen the parameters in the sidebar or wait for more reports.") -> None:
    st.markdown(
        f"""
        <div class="ws-sent-empty">
          <div class="ws-sent-empty-title">Sentinel idle 🟢</div>
          <div>{hint}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_sparkline(counts, accent: str, *, window_label: str) -> str:
    if not counts:
        return ""
    mx = max(counts) or 1
    bars = "".join(
        f"<div class='ws-sent-spark-bar{(' empty' if v == 0 else '')}' "
        f"style='height:{int(2 + (v / mx) * 26)}px;'></div>"
        for v in counts
    )
    n = len(counts)
    return (
        f"<div class='ws-sent-spark-wrap' style='--accent:{accent};'>"
        f"<div class='ws-sent-spark-kicker'>Activity · last {window_label}</div>"
        f"<div class='ws-sent-sparkline'>{bars}</div>"
        f"<div class='ws-sent-spark-axis'>"
        f"<span>{n}d ago</span><span>peak {mx}</span><span>today</span>"
        f"</div></div>"
    )


def render_sentinel_clusters(clusters, user_loc, *, recommended_action_fn=None) -> None:
    """Render the per-cluster intel cards.

    `user_loc` is a dict with `lat`/`lon`. `recommended_action_fn(cluster, lat, lon) -> str`
    is injected from sentinel.py to avoid a hard import cycle.
    """
    if not clusters:
        render_sentinel_empty()
        return

    from sentinel import CATEGORY_ICON  # local import

    for c in clusters:
        accent = _cluster_status_hue(c.status)
        accent_bg = _hex_to_rgba(accent, 0.16)
        accent_bd = _hex_to_rgba(accent, 0.36)
        action_bg = _hex_to_rgba(accent, 0.08)

        # velocity bar: cap visualisation at 4× for sanity, but show numeric
        cap = 4.0
        width_pct = min(100, int(round(c.velocity / cap * 100)))
        baseline_left = 25.0  # 1.0 / 4.0 → 25%

        # 4-cell stat grid
        statgrid = "".join([
            f"<div class='ws-sent-statgrid-cell'><div class='ws-sent-statgrid-val'>{c.recent_count}</div><div class='ws-sent-statgrid-lbl'>Recent ({c.recent_window_days}d)</div></div>",
            f"<div class='ws-sent-statgrid-cell'><div class='ws-sent-statgrid-val'>{c.baseline_count}</div><div class='ws-sent-statgrid-lbl'>Prior ({c.baseline_window_days}d)</div></div>",
            f"<div class='ws-sent-statgrid-cell'><div class='ws-sent-statgrid-val'>{c.severity_mean:.1f}<span style='color:{MUTED}; font-size:.7rem; font-weight:600;'> /5</span></div><div class='ws-sent-statgrid-lbl'>Severity</div></div>",
            f"<div class='ws-sent-statgrid-cell'><div class='ws-sent-statgrid-val'>{int(round(c.verified_frac * 100))}<span style='color:{MUTED}; font-size:.7rem; font-weight:600;'> %</span></div><div class='ws-sent-statgrid-lbl'>Verified</div></div>",
        ])

        mix_html = "".join(
            f"<div class='ws-sent-mix-tag'>{CATEGORY_ICON.get(cat, '·')} {cat} <strong>×{n}</strong></div>"
            for cat, n in c.category_mix
        )

        action = recommended_action_fn(c, user_loc["lat"], user_loc["lon"]) if recommended_action_fn else ""
        action_html = f"<div class='ws-sent-action' style='--accent:{accent}; --action-bg:{action_bg};'>{action}</div>" if action else ""

        spark = _render_sparkline(c.daily_counts, accent, window_label=f"{c.recent_window_days} d")

        peak_lbl = f"peak {c.peak_hour:02d}:00" if c.peak_hour is not None else "no peak"
        last_lbl = c.last_seen.strftime("%a %d %b · %H:%M") if c.last_seen else "—"
        sub = (
            f"center {c.center_lat:.4f}, {c.center_lon:.4f} · radius {c.radius_km:g} km · "
            f"last seen {last_lbl} ({c.days_since_last:.1f} d ago) · {peak_lbl}"
        )

        st.markdown(
            f"""
            <div class="ws-sent-cluster"
                 style="--accent:{accent}; --accent-bg:{accent_bg}; --accent-bd:{accent_bd};">
              <div class="ws-sent-cluster-head">
                <div class="ws-sent-cluster-icon">{c.icon}</div>
                <div>
                  <div class="ws-sent-cluster-title">Cluster #{c.id + 1} · {c.dominant_category.title()} <span style="color:{MUTED}; font-weight:600;">· {c.count} incidents</span></div>
                  <div class="ws-sent-cluster-sub">{sub}</div>
                </div>
                <div class="ws-sent-cluster-status">{c.status}</div>
              </div>

              <div class="ws-sent-velbar-wrap">
                <div class="ws-sent-velbar-baseline-lbl" style="left:{baseline_left}%;">1.0×</div>
                <div class="ws-sent-velbar"><div class="ws-sent-velbar-fill" style="width:{width_pct}%;"></div></div>
                <div class="ws-sent-velbar-baseline" style="left:{baseline_left}%;"></div>
                <div class="ws-sent-vel-meta">
                  <span>recent {c.recent_rate:.2f}/d · baseline {c.baseline_rate:.2f}/d</span>
                  <span class="ws-sent-vel-current">{c.velocity:.2f}× baseline</span>
                </div>
              </div>

              <div class="ws-sent-statgrid">{statgrid}</div>
              <div class="ws-sent-mix">{mix_html}</div>
              {spark}
              {action_html}
            </div>
            """,
            unsafe_allow_html=True,
        )


# ----------------------------- Travel Advisory -----------------------------

from datetime import timedelta as _adv_timedelta  # noqa: E402

_ADV_LEVEL_HUE = {
    "Critical":  "#EF4444",
    "Elevated":  "#F59E0B",
    "Caution":   "#FBBF24",
    "All clear": "#10B981",
}

_ADV_LEVEL_ICON = {
    "Critical":  "🛑",
    "Elevated":  "⚠️",
    "Caution":   "⚠️",
    "All clear": "✅",
}

_SEVERITY_HUE = {5: "#FF3D60", 4: "#FF7F50", 3: "#F9C440", 2: "#3DA9FC"}

_CATEGORY_ICON = {
    "accident":  "🚗",
    "flooding":  "🌊",
    "landslide": "⛰️",
    "roadblock": "🚧",
    "other":     "⚠️",
}


def _esc(s) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _rec_to_html(text: str) -> str:
    """Lightweight markdown: bold (`**x**`) only. Everything else escaped."""
    out: list[str] = []
    parts = _esc(text).split("**")
    for i, chunk in enumerate(parts):
        if i % 2 == 1:
            out.append(f"<strong>{chunk}</strong>")
        else:
            out.append(chunk)
    return "".join(out)


def render_advisory_brief(brief, *, scan_caption: bool = True) -> None:
    """Render the full travel-advisory card stack for one `AdvisoryBrief`."""
    hue = _ADV_LEVEL_HUE.get(brief.advisory_level, brief.level_color)
    icon = _ADV_LEVEL_ICON.get(brief.advisory_level, "")
    glow = _hex_to_rgba(hue, 0.22)
    stripe_bg = _hex_to_rgba(hue, 0.16)
    stripe_bd = _hex_to_rgba(hue, 0.32)

    pulse_caption = ""
    if brief.risk_pulse_status and brief.risk_pulse_status != "Unknown":
        pulse_caption = (
            f" · area pulse <strong style='color:#E6E9F2;'>{_esc(brief.risk_pulse_status)}</strong>"
        )

    # Hero card
    st.markdown(
        f"""
        <div class="ws-adv-hero" style="--adv-hue:{hue}; --adv-glow:{glow};
                                        --adv-stripe-bg:{stripe_bg}; --adv-stripe-bd:{stripe_bd};">
          <div class="ws-adv-hero-inner">
            <div class="ws-ring" style="--pct:{brief.safety.score}; --ring:{hue};">
              <div class="ws-ring-inner">
                <div class="ws-ring-val" style="color:{hue}">{brief.safety.score}</div>
                <div class="ws-ring-band" style="color:{hue}">{_esc(brief.safety.band)}</div>
              </div>
            </div>
            <div style="flex:1; min-width:0;">
              <span class="ws-adv-stripe">
                <span class="ws-adv-stripe-dot"></span>
                {icon} {_esc(brief.advisory_level)}
              </span>
              <div class="ws-adv-title">{_esc(brief.target_label)}</div>
              <div class="ws-adv-coords">
                ({brief.target_lat:.4f}, {brief.target_lon:.4f})
                · scan {brief.radius_km:g} km · lookback {brief.lookback_days}d
                {pulse_caption}
              </div>
              <div class="ws-adv-headline">{_esc(brief.level_headline)}</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # KPI tiles
    nearest_help_str = (
        f"{brief.help_pois[0].distance_km:.1f} km"
        if brief.help_pois else "—"
    )
    nearest_help_sub = (
        _esc(brief.help_pois[0].name) if brief.help_pois else "no help POIs"
    )
    best_window = brief.best_windows[0] if brief.best_windows else None
    window_val = best_window.label if best_window else "—"
    window_sub = (
        f"top-cell risk {int(best_window.risk * 100)}%"
        if best_window else "no forecast available"
    )
    cluster_val = str(len(brief.nearby_clusters))
    cluster_sub = (
        f"{brief.severe_cluster_count} escalating"
        if brief.severe_cluster_count else "none escalating"
    )
    st.markdown(
        f"""
        <div class="ws-adv-tiles">
          <div class="ws-adv-tile">
            <div class="ws-adv-tile-kicker">Incidents nearby</div>
            <div class="ws-adv-tile-val">{brief.safety.incidents_nearby}</div>
            <div class="ws-adv-tile-sub">last {brief.lookback_days}d · within {brief.radius_km:g} km</div>
          </div>
          <div class="ws-adv-tile">
            <div class="ws-adv-tile-kicker">Live clusters</div>
            <div class="ws-adv-tile-val">{cluster_val}</div>
            <div class="ws-adv-tile-sub">{cluster_sub}</div>
          </div>
          <div class="ws-adv-tile">
            <div class="ws-adv-tile-kicker">Safer depart window</div>
            <div class="ws-adv-tile-val">{_esc(window_val)}</div>
            <div class="ws-adv-tile-sub">{_esc(window_sub)}</div>
          </div>
          <div class="ws-adv-tile">
            <div class="ws-adv-tile-kicker">Nearest help</div>
            <div class="ws-adv-tile-val">{_esc(nearest_help_str)}</div>
            <div class="ws-adv-tile-sub">{nearest_help_sub}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Two-column section: recent incidents + 7d sparkline | clusters + windows
    left, right = st.columns([3, 2])

    with left:
        st.markdown(
            f"""
            <div class="ws-adv-section">
              <div class="ws-adv-section-title">
                <span>📌 Recent incidents</span>
                <span style="margin-left:auto; color:{MUTED}; text-transform:none; letter-spacing:0; font-weight:500;">
                  {brief.safety.incidents_nearby} in the last {brief.lookback_days} days
                </span>
              </div>
            """,
            unsafe_allow_html=True,
        )
        if brief.recent_incidents:
            for s in brief.recent_incidents[:6]:
                inc_hue = _SEVERITY_HUE.get(s.severity, "#F9C440")
                inc_shadow = _hex_to_rgba(inc_hue, 0.22)
                cat_icon = _CATEGORY_ICON.get(s.category, "⚠️")
                status_cls = "verified" if s.status == "verified" else "pending"
                note_html = (
                    f'<div class="ws-adv-inc-note">"{_esc(s.note)}"</div>'
                    if s.note else '<div class="ws-adv-inc-note"></div>'
                )
                st.markdown(
                    f"""
                    <div class="ws-adv-inc-row" style="--inc-hue:{inc_hue}; --inc-shadow:{inc_shadow};">
                      <div class="ws-adv-inc-dot"></div>
                      <div class="ws-adv-inc-cat">{cat_icon} {_esc(s.category)}</div>
                      <div class="ws-adv-inc-dist">{s.distance_km:.1f} km</div>
                      <div class="ws-adv-inc-when">{_esc(s.when)}</div>
                      {note_html}
                      <div class="ws-adv-inc-status {status_cls}">{_esc(s.status)}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            if len(brief.recent_incidents) > 6:
                st.caption(f"+ {len(brief.recent_incidents) - 6} more not shown")
        else:
            st.markdown(
                f"<div class='ws-adv-empty'>No incidents within {brief.radius_km:g} km in the "
                f"last {brief.lookback_days} days.</div>",
                unsafe_allow_html=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)

        # 7-day sparkline
        trend = brief.incident_trend or []
        if trend:
            mx = max(trend) or 1
            bars = "".join(
                (
                    f'<div class="ws-adv-spark-bar" style="height:{max(6, int(v / mx * 100))}%;"></div>'
                    if v > 0
                    else '<div class="ws-adv-spark-bar ws-adv-spark-empty"></div>'
                )
                for v in trend
            )
            labels = "".join(
                f"<span>{(brief.generated_at - _adv_timedelta(days=brief.lookback_days - 1 - i)).strftime('%a')}</span>"
                for i in range(brief.lookback_days)
            )
            st.markdown(
                f"""
                <div class="ws-adv-section">
                  <div class="ws-adv-section-title">
                    <span>📈 Incident trend · last {brief.lookback_days} days</span>
                    <span style="margin-left:auto; color:{MUTED}; text-transform:none; letter-spacing:0; font-weight:500;">
                      max {max(trend)}/day · total {sum(trend)}
                    </span>
                  </div>
                  <div class="ws-adv-spark" style="--adv-hue:{hue};">{bars}</div>
                  <div class="ws-adv-spark-labels">{labels}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    with right:
        # Nearby clusters
        st.markdown(
            '<div class="ws-adv-section">'
            '<div class="ws-adv-section-title"><span>🛰️ Live clusters near here</span></div>',
            unsafe_allow_html=True,
        )
        if brief.nearby_clusters:
            for cl in brief.nearby_clusters[:5]:
                c_hue = _cluster_status_hue(cl.velocity_status)
                c_bg = _hex_to_rgba(c_hue, 0.14)
                c_bd = _hex_to_rgba(c_hue, 0.30)
                cat_icon = _CATEGORY_ICON.get(cl.dominant_category, "⚠️")
                dist_txt = "overlapping" if cl.distance_km <= 0.05 else f"{cl.distance_km:.1f} km away"
                st.markdown(
                    f"""
                    <div class="ws-adv-cluster">
                      <span class="ws-adv-cluster-pill"
                            style="--cluster-hue:{c_hue}; --cluster-bg:{c_bg}; --cluster-bd:{c_bd};">
                        {_esc(cl.velocity_status)}
                      </span>
                      <div style="flex:1; min-width:0;">
                        <div style="color:#E6E9F2; font-weight:700;">
                          {cat_icon} {_esc(cl.dominant_category)} · {cl.members} reports
                        </div>
                        <div style="color:{MUTED}; font-size:.78rem;">
                          {dist_txt} · r={cl.radius_km:.1f} km · last {cl.days_since_last:g}d ago
                        </div>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                "<div class='ws-adv-empty'>No active clusters overlap this scan radius.</div>",
                unsafe_allow_html=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)

        # Best windows
        st.markdown(
            '<div class="ws-adv-section">'
            '<div class="ws-adv-section-title"><span>🕒 Safer depart windows · next 12h</span></div>',
            unsafe_allow_html=True,
        )
        if brief.best_windows:
            for w in brief.best_windows:
                pct = max(2, int(w.risk * 100))
                st.markdown(
                    f"""
                    <div class="ws-adv-window">
                      <div class="ws-adv-window-label">{_esc(w.label)}</div>
                      <div class="ws-adv-window-bar">
                        <div class="ws-adv-window-bar-fill" style="width:{pct}%;"></div>
                      </div>
                      <div class="ws-adv-window-pct">{int(w.risk * 100)}%</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                "<div class='ws-adv-empty'>No forecast samples available.</div>",
                unsafe_allow_html=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)

    # Help POIs
    if brief.help_pois:
        st.markdown(
            '<div class="ws-adv-section">'
            '<div class="ws-adv-section-title"><span>🏥 Nearest help</span></div>'
            '<div class="ws-card" style="padding:8px 0;">',
            unsafe_allow_html=True,
        )
        ptype_icon = {
            "hospital": "🏥", "police": "🚓", "clinic": "➕",
            "fire": "🚒", "tourist_help_desk": "ℹ️",
        }
        for p in brief.help_pois:
            icon = ptype_icon.get(p.ptype.lower(), "📍")
            st.markdown(
                f"""
                <div class="ws-adv-poi">
                  <div class="ws-adv-poi-icon">{icon}</div>
                  <div class="ws-adv-poi-name">{_esc(p.name)}</div>
                  <div class="ws-adv-poi-type">{_esc(p.ptype)}</div>
                  <div class="ws-adv-poi-dist">{p.distance_km:.1f} km</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        st.markdown("</div></div>", unsafe_allow_html=True)

    # Recommendations
    st.markdown(
        '<div class="ws-adv-section">'
        '<div class="ws-adv-section-title"><span>🧭 What to do next</span></div>',
        unsafe_allow_html=True,
    )
    for i, rec in enumerate(brief.recommendations, 1):
        st.markdown(
            f"""
            <div class="ws-adv-rec" style="--adv-hue:{hue};">
              <div class="ws-adv-rec-num">{i}</div>
              <div class="ws-adv-rec-text">{_rec_to_html(rec)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)

    if scan_caption:
        st.caption(
            f"Brief generated at {brief.generated_at:%Y-%m-%d %H:%M} UTC · "
            f"schema waysafe.advisory.v1"
        )


def render_advisory_empty(hint: str = "Pick a destination above to generate a safety brief.") -> None:
    st.markdown(
        f"""
        <div class="ws-sent-empty">
          <div class="ws-sent-empty-title">No brief yet</div>
          <div>{_esc(hint)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------- Compass


_CMP_LEVEL_HUE = {
    "Critical":  "#EF4444",
    "Elevated":  "#F59E0B",
    "Caution":   "#FBBF24",
    "All clear": "#10B981",
}


def _goodness_hue(g: float) -> str:
    """0..1 → red→amber→green hue for heat-mapped matrix cells (1 = safest)."""
    g = max(0.0, min(1.0, g))
    red, amber, green = (239, 68, 68), (251, 191, 36), (16, 185, 129)
    if g <= 0.5:
        t = g / 0.5
        a, b = red, amber
    else:
        t = (g - 0.5) / 0.5
        a, b = amber, green
    rgb = tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))
    return "#%02X%02X%02X" % rgb


def render_compass(result) -> None:
    """Render the full Compass showdown: verdict hero, podium, factor matrix."""
    dests = result.destinations
    if not dests:
        render_compass_empty()
        return

    win = result.winner
    hue = _CMP_LEVEL_HUE.get(win.advisory_level, win.level_color)
    glow = _hex_to_rgba(hue, 0.20)

    margin_html = ""
    if result.runner_up is not None:
        margin_html = (
            f'<div class="ws-cmp-margin" style="--hue:{hue};">'
            f'<div class="ws-cmp-margin-val">+{result.margin}</div>'
            f'<div class="ws-cmp-margin-lbl">pts ahead</div></div>'
        )

    st.markdown(
        f"""
        <div class="ws-cmp-hero" style="--hue:{hue}; --glow:{glow};">
          <div class="ws-ring" style="--pct:{win.compass_score}; --ring:{hue};">
            <div class="ws-ring-inner">
              <div class="ws-ring-val" style="color:{hue}">{win.compass_score}</div>
              <div class="ws-ring-band" style="color:{hue}">COMPASS</div>
            </div>
          </div>
          <div class="ws-cmp-hero-body">
            <span class="ws-cmp-crown">🏆 Safest pick · {_esc(win.advisory_level)}</span>
            <div class="ws-cmp-hero-title">{_esc(result.verdict_headline)}</div>
            <div class="ws-cmp-hero-detail">{_rec_to_html(result.verdict_detail)}</div>
            <div class="ws-cmp-hero-meta">
              Depart {result.depart:%a %d %b · %H:%M} · scan {result.radius_km:g} km ·
              {len(dests)} destinations compared
            </div>
          </div>
          {margin_html}
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Podium cards
    cards = []
    for v in dests:
        lvl_hue = _CMP_LEVEL_HUE.get(v.advisory_level, v.level_color)
        bar_hue = _goodness_hue(v.compass_score / 100.0)
        help_s = f"{v.nearest_help_km:.1f}" if v.nearest_help_km is not None else "—"
        winner_cls = " is-winner" if v.is_winner else ""
        rank_cls = f"r{v.rank}" if v.rank <= 3 else ""
        cards.append(
            f"""
            <div class="ws-cmp-card{winner_cls}" style="--hue:{lvl_hue};">
              <div class="ws-cmp-card-top">
                <span class="ws-cmp-rank {rank_cls}">{v.rank}</span>
                <span class="ws-cmp-level" style="color:{lvl_hue}; border:1px solid {_hex_to_rgba(lvl_hue, 0.45)};">
                  {_esc(v.advisory_level)}
                </span>
              </div>
              <div class="ws-cmp-card-name">{_esc(v.label)}</div>
              <div class="ws-cmp-card-score">
                <b style="color:{bar_hue}">{v.compass_score}</b><span>/ 100 compass</span>
              </div>
              <div class="ws-cmp-bar-track">
                <div class="ws-cmp-bar-fill" style="width:{v.compass_score}%; background:{bar_hue};"></div>
              </div>
              <div class="ws-cmp-mini">
                <div class="ws-cmp-mini-cell"><div class="ws-cmp-mini-val">{v.incidents_nearby}</div>
                  <div class="ws-cmp-mini-lbl">incidents</div></div>
                <div class="ws-cmp-mini-cell"><div class="ws-cmp-mini-val">{help_s}</div>
                  <div class="ws-cmp-mini-lbl">help km</div></div>
                <div class="ws-cmp-mini-cell"><div class="ws-cmp-mini-val">{int(round(v.forecast_risk * 100))}%</div>
                  <div class="ws-cmp-mini-lbl">forecast</div></div>
              </div>
              <div class="ws-cmp-card-head">{_esc(v.headline)}</div>
            </div>
            """
        )
    st.markdown(
        f'<div class="ws-cmp-podium">{"".join(cards)}</div>',
        unsafe_allow_html=True,
    )

    # Comparison matrix — destinations as columns, factors as heat-mapped rows
    n = len(dests)
    cols = f"1.35fr repeat({n}, minmax(0,1fr))"
    parts = [f'<div class="ws-cmp-matrix" style="grid-template-columns:{cols};">']
    parts.append('<div class="ws-cmp-mcorner">Factor ↓ / Destination →</div>')
    for v in dests:
        wc = " is-winner" if v.is_winner else ""
        lvl_hue = _CMP_LEVEL_HUE.get(v.advisory_level, v.level_color)
        parts.append(f'<div class="ws-cmp-mhead{wc}" style="--hue:{lvl_hue};">{_esc(v.label)}</div>')

    # Headline Compass-score row
    parts.append('<div class="ws-cmp-mlabel"><strong>Compass score</strong></div>')
    for v in dests:
        g = v.compass_score / 100.0
        ch = _goodness_hue(g)
        parts.append(
            f'<div class="ws-cmp-cell head-row" style="background:{_hex_to_rgba(ch, 0.18)}; color:{ch};">'
            f'{v.compass_score}</div>'
        )

    # Per-factor rows
    for fi, (_key, label) in enumerate(result.factor_order):
        parts.append(f'<div class="ws-cmp-mlabel">{_esc(label)}</div>')
        for v in dests:
            f = v.factors[fi]
            ch = _goodness_hue(f.goodness)
            parts.append(
                f'<div class="ws-cmp-cell" style="background:{_hex_to_rgba(ch, 0.15)}; color:{ch};">'
                f'{_esc(f.display)}</div>'
            )
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)
    st.caption("Greener = safer on that factor. Compass blends safety, the depart-time forecast, and live-cluster pressure.")


def render_compass_empty(hint: str = "Pick at least two destinations above, then run the showdown.") -> None:
    st.markdown(
        f"""
        <div class="ws-sent-empty">
          <div class="ws-sent-empty-title">No comparison yet</div>
          <div>{_esc(hint)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------- StaySafe

_STAY_LEVEL_HUE = {
    "Critical":  "#EF4444",
    "Elevated":  "#F59E0B",
    "Caution":   "#FBBF24",
    "All clear": "#10B981",
}

_STAY_KIND_LABEL = {
    "hotel":    "Hotel",
    "hostel":   "Hostel",
    "homestay": "Homestay",
    "villa":    "Villa",
    "resort":   "Resort",
}


def _spark_html(curve, *, max_val: float = 1.0) -> str:
    """24-hour risk sparkline. Each bar's hue and height encodes risk."""
    if not curve:
        return ""
    parts = ['<div class="ws-stay-spark">']
    for v in curve:
        v = max(0.0, min(max_val, float(v)))
        h = max(2, int(round(v / max_val * 30)))   # 2..30 px
        hue = _goodness_hue(1.0 - (v / max_val))
        parts.append(
            f'<div class="ws-stay-spark-bar" style="height:{h}px; background:{hue};"></div>'
        )
    parts.append("</div>")
    parts.append('<div class="ws-stay-spark-axis"><span>00</span>'
                 '<span>06</span><span>12</span><span>18</span><span>24</span></div>')
    return "".join(parts)


def _hr_to_str(risk: float) -> str:
    return f"{int(round(float(risk) * 100))}%"


def _stay_card_html(v) -> str:
    """One stay card for the podium row."""
    lvl_hue = _STAY_LEVEL_HUE.get(v.level, v.level_color)
    bar_hue = _goodness_hue(v.stay_score / 100.0)
    winner_cls = " is-winner" if v.is_winner else ""
    rank_cls = f"r{v.rank}" if v.rank <= 3 else ""
    kind_label = _STAY_KIND_LABEL.get(v.candidate.kind.lower(),
                                       v.candidate.kind or "Stay")

    spark = _spark_html(v.hourly_risk) if v.hourly_risk else ""

    return f"""
        <div class="ws-stay-card{winner_cls}" style="--hue:{lvl_hue};">
          <div class="ws-stay-card-top">
            <div style="display:flex; align-items:center; gap:8px;">
              <span class="ws-stay-rank {rank_cls}">{v.rank}</span>
              <span class="ws-stay-kind">{_esc(kind_label)}</span>
            </div>
            <span class="ws-stay-level" style="color:{lvl_hue}; border:1px solid {_hex_to_rgba(lvl_hue, 0.45)};">
              {_esc(v.level)}
            </span>
          </div>
          <div class="ws-stay-card-name" title="{_esc(v.candidate.name)}">{_esc(v.candidate.name)}</div>
          <div class="ws-stay-card-score">
            <b style="color:{bar_hue}">{v.stay_score}</b><span>/ 100 stay-safe</span>
          </div>
          <div class="ws-stay-bar-track">
            <div class="ws-stay-bar-fill" style="width:{v.stay_score}%; background:{bar_hue};"></div>
          </div>
          <div class="ws-stay-tri">
            <div class="ws-stay-tri-cell">
              <div class="ws-stay-tri-val">{_hr_to_str(v.sleep_risk_mean)}</div>
              <div class="ws-stay-tri-lbl">Sleep</div>
            </div>
            <div class="ws-stay-tri-cell">
              <div class="ws-stay-tri-val">{_hr_to_str(v.evening_risk_mean)}</div>
              <div class="ws-stay-tri-lbl">Evening</div>
            </div>
            <div class="ws-stay-tri-cell">
              <div class="ws-stay-tri-val">{_hr_to_str(v.morning_risk_mean)}</div>
              <div class="ws-stay-tri-lbl">Morning</div>
            </div>
          </div>
          {spark}
          <div class="ws-stay-card-head">{_esc(v.headline)}</div>
          <div class="ws-stay-why">{_esc(v.why_pick)}</div>
        </div>
    """


def _help_legs_html(v) -> str:
    """3-column hospital/police/clinic walk breakdown for the winner card."""
    if not v.help_legs:
        return ""
    parts = ['<div class="ws-stay-legs">']
    for leg in v.help_legs:
        if leg.distance_km is None:
            name = "— no nearby option in dataset"
            meta = "—"
            bar_w = 0
            hue = "#6B7280"
        else:
            name = leg.name or "(unnamed)"
            mins = f"{leg.walk_min} min" if leg.walk_min is not None else "—"
            meta = f"{leg.distance_km:.1f} km · {mins} walk"
            bar_w = int(round(leg.goodness * 100))
            hue = _goodness_hue(leg.goodness)
        cat_label = leg.category.upper()
        parts.append(
            f"""
            <div class="ws-stay-leg" style="--hue:{hue};">
              <div class="ws-stay-leg-cat">{_esc(cat_label)}</div>
              <div class="ws-stay-leg-name" title="{_esc(name)}">{_esc(name)}</div>
              <div class="ws-stay-leg-meta">{_esc(meta)}</div>
              <div class="ws-stay-leg-bar">
                <div class="ws-stay-leg-bar-fill"
                     style="width:{bar_w}%; background:{hue};"></div>
              </div>
            </div>
            """
        )
    parts.append("</div>")
    return "".join(parts)


def render_staysafe(result) -> None:
    """Hero verdict + podium + matrix + help-legs for one StayComparisonResult."""
    stays = result.stays
    if not stays:
        render_staysafe_empty()
        return

    win = result.winner
    hue = _STAY_LEVEL_HUE.get(win.level, win.level_color)
    glow = _hex_to_rgba(hue, 0.20)

    margin_html = ""
    if result.runner_up is not None:
        margin_html = (
            f'<div class="ws-stay-margin" style="--hue:{hue};">'
            f'<div class="ws-stay-margin-val">+{result.margin}</div>'
            f'<div class="ws-stay-margin-lbl">pts ahead</div></div>'
        )

    profile_chip = (
        f'<span class="ws-stay-chip profile" style="--hue:{hue};">{_esc(result.profile)}</span>'
    )
    nights_label = f"{result.nights} night" + ("s" if result.nights != 1 else "")

    st.markdown(
        f"""
        <div class="ws-stay-hero" style="--hue:{hue}; --glow:{glow};">
          <div class="ws-ring" style="--pct:{win.stay_score}; --ring:{hue};">
            <div class="ws-ring-inner">
              <div class="ws-ring-val" style="color:{hue}">{win.stay_score}</div>
              <div class="ws-ring-band" style="color:{hue}">STAY-SAFE</div>
            </div>
          </div>
          <div class="ws-stay-hero-body">
            <span class="ws-stay-crown">🛏️ Recommended stay · {_esc(win.level)}</span>
            <div class="ws-stay-hero-title">{_rec_to_html(result.verdict_headline)}</div>
            <div class="ws-stay-hero-detail">{_rec_to_html(result.verdict_detail)}</div>
            <div class="ws-stay-hero-meta">
              {profile_chip}
              <span class="ws-stay-chip">Check-in {result.check_in:%a %d %b · %H:%M}</span>
              <span class="ws-stay-chip">{_esc(nights_label)}</span>
              <span class="ws-stay-chip">{len(stays)} stays compared</span>
            </div>
          </div>
          {margin_html}
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Podium row
    cards = [_stay_card_html(v) for v in stays]
    st.markdown(
        f'<div class="ws-stay-podium">{"".join(cards)}</div>',
        unsafe_allow_html=True,
    )

    # Winner-detail: help legs (closeup) — only render for the winner
    if win:
        st.markdown(
            f"<div style='font-size:.78rem; color:#AAB2C5; margin: 6px 4px 0; "
            f"letter-spacing:.06em; text-transform:uppercase; font-weight:700;'>"
            f"Walk to help · from {_esc(win.candidate.name)}</div>",
            unsafe_allow_html=True,
        )
        st.markdown(_help_legs_html(win), unsafe_allow_html=True)

    # Heat-mapped comparison matrix
    n = len(stays)
    cols = f"1.55fr repeat({n}, minmax(0,1fr))"
    parts = [f'<div class="ws-stay-matrix" style="grid-template-columns:{cols};">']
    parts.append('<div class="ws-stay-mcorner">Factor ↓ / Stay →</div>')
    for v in stays:
        wc = " is-winner" if v.is_winner else ""
        lvl_hue = _STAY_LEVEL_HUE.get(v.level, v.level_color)
        parts.append(
            f'<div class="ws-stay-mhead{wc}" style="--hue:{lvl_hue};" '
            f'title="{_esc(v.candidate.name)}">{_esc(v.candidate.name)}</div>'
        )

    # Headline stay-score row
    parts.append('<div class="ws-stay-mlabel"><strong>Stay-safe score</strong></div>')
    for v in stays:
        g = v.stay_score / 100.0
        ch = _goodness_hue(g)
        parts.append(
            f'<div class="ws-stay-cell head-row" '
            f'style="background:{_hex_to_rgba(ch, 0.18)}; color:{ch};">'
            f'{v.stay_score}</div>'
        )

    # Per-factor rows with weight chip
    for fi, (_key, label) in enumerate(result.factor_order):
        w_pct = int(round(stays[0].factors[fi].weight * 100))
        parts.append(
            f'<div class="ws-stay-mlabel">{_esc(label)}'
            f'<span class="ws-stay-mlabel-w">{w_pct}%</span></div>'
        )
        for v in stays:
            f = v.factors[fi]
            ch = _goodness_hue(f.goodness)
            parts.append(
                f'<div class="ws-stay-cell" '
                f'style="background:{_hex_to_rgba(ch, 0.15)}; color:{ch};">'
                f'{_esc(f.display)}'
                f'<span class="ws-stay-cell-sub">{int(round(f.contribution))} pts</span>'
                f'</div>'
            )
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)
    st.caption(
        "Greener = safer on that factor. Per-cell sub-value = weighted "
        "contribution to the 0–100 stay-safe score. Weights vary by profile."
    )


def render_staysafe_empty(hint: str = "Pick at least two stays above, then run the comparison.") -> None:
    st.markdown(
        f"""
        <div class="ws-sent-empty">
          <div class="ws-sent-empty-title">No stay comparison yet</div>
          <div>{_esc(hint)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================== Refuge


_REF_BAND_HUE = {
    "Strong refuge": "#10B981",
    "Viable refuge": "#FBBF24",
    "Last resort":   "#F59E0B",
    "Not a refuge":  "#EF4444",
}


def _ref_corridor_strip_html(samples) -> str:
    if not samples:
        return ""
    steps = []
    for s in samples:
        # 1 − risk to get goodness, then map to red→amber→green.
        hue = _goodness_hue(1.0 - float(s.risk))
        cls = "ws-ref-corridor-step"
        if getattr(s, "in_geofence", False):
            cls += " fenced"
        steps.append(
            f'<div class="{cls}" style="--step-hue:{hue};" '
            f'title="risk {s.risk:.2f}{(" · in risk zone" if s.in_geofence else "")}"></div>'
        )
    return f'<div class="ws-ref-corridor">{"".join(steps)}</div>'


def _ref_card_html(opt) -> str:
    band_hue = _REF_BAND_HUE.get(opt.band, opt.band_color)
    bar_hue = _goodness_hue(opt.refuge_score / 100.0)
    top_cls = " is-top" if opt.is_top else ""
    rank_cls = "r1" if opt.rank == 1 else ""
    notes_html = ""
    if opt.notes:
        notes_html = (
            "<div class='ws-ref-notes'><ul>"
            + "".join(f"<li>{_esc(n)}</li>" for n in opt.notes[:3])
            + "</ul></div>"
        )
    return f"""
    <div class="ws-ref-card{top_cls}" style="--hue:{band_hue}; --glow:{_hex_to_rgba(band_hue, 0.18)};">
      <div class="ws-ref-card-top">
        <span class="ws-ref-rank {rank_cls}">#{opt.rank}</span>
        <span class="ws-ref-band" style="color:{band_hue}; background:{_hex_to_rgba(band_hue, 0.18)};">
          {_esc(opt.band)}
        </span>
      </div>
      <div class="ws-ref-tier">{opt.tier_icon} {_esc(opt.tier_label)}</div>
      <div class="ws-ref-card-name">{_esc(opt.poi_name)}</div>
      <div class="ws-ref-card-score">
        <b style="color:{bar_hue}">{opt.refuge_score}</b><span>/ 100 refuge</span>
      </div>
      <div class="ws-ref-bar-track">
        <div class="ws-ref-bar-fill" style="width:{opt.refuge_score}%; background:{bar_hue};"></div>
      </div>
      <div class="ws-ref-mini">
        <div class="ws-ref-mini-cell">
          <div class="ws-ref-mini-val">{opt.distance_km*1000:.0f}m</div>
          <div class="ws-ref-mini-lbl">distance</div>
        </div>
        <div class="ws-ref-mini-cell">
          <div class="ws-ref-mini-val">{opt.eta_min:.0f}m</div>
          <div class="ws-ref-mini-lbl">walk</div>
        </div>
        <div class="ws-ref-mini-cell">
          <div class="ws-ref-mini-val">{opt.bearing_label}</div>
          <div class="ws-ref-mini-lbl">heading</div>
        </div>
      </div>
      {_ref_corridor_strip_html(opt.path_samples)}
      <div class="ws-ref-script">→ {_esc(opt.arrival_script)}</div>
      {notes_html}
    </div>
    """


def render_refuge(result) -> None:
    """Render the full Refuge result: bearing-compass hero, podium, matrix,
    emergency card and quiet-beacon payload."""
    options = result.options
    here_hue = band_color(result.here_band)

    if not options:
        # Fallback: still render the local safety score + emergency card.
        st.markdown(
            f"""
            <div class="ws-ref-empty">
              <div class="ws-ref-empty-title">No registered refuge within {result.radius_km:g} km</div>
              <div>{_esc(result.advisory_line)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        _render_emergency_card(result.emergency_card)
        return

    top = options[0]
    hue = _REF_BAND_HUE.get(top.band, top.band_color)
    glow = _hex_to_rgba(hue, 0.24)

    fence_chip = ""
    if top.geofence_crossings >= 1:
        fence_chip = (
            f'<span class="ws-ref-chip warn">'
            f'corridor clips {top.geofence_crossings} risk waypoint'
            f'{"s" if top.geofence_crossings != 1 else ""}'
            f'</span>'
        )

    here_chip_hue = here_hue
    here_chip = (
        f'<span class="ws-ref-chip" style="border-color:{here_chip_hue}; color:{here_chip_hue};">'
        f'you · {_esc(result.here_band)} {result.here_score}'
        f'</span>'
    )

    st.markdown(
        f"""
        <div class="ws-ref-hero" style="--hue:{hue}; --glow:{glow};">
          <div class="ws-ref-compass" style="--hue:{hue}; --pct:{top.refuge_score}; --glow:{glow};">
            <div class="ws-ref-compass-inner">
              <div class="ws-ref-compass-arrow" style="--bearing:{top.bearing_deg}deg;">↑</div>
              <span class="ws-ref-compass-label">{_esc(top.bearing_label)}</span>
              <span class="ws-ref-compass-sub">{top.bearing_deg}° · {top.refuge_score}/100</span>
            </div>
          </div>
          <div class="ws-ref-hero-body">
            <span class="ws-ref-pill">Refuge · {_esc(top.band)}</span>
            <div class="ws-ref-hero-title">{_rec_to_html(result.headline)}</div>
            <div class="ws-ref-hero-detail">{_rec_to_html(result.advisory_line)}</div>
            <div class="ws-ref-hero-meta">
              {here_chip}
              <span class="ws-ref-chip">scan {result.radius_km:g} km</span>
              <span class="ws-ref-chip">{len(options)} options ranked</span>
              <span class="ws-ref-chip">{result.now:%H:%M}</span>
              {fence_chip}
            </div>
          </div>
          <div class="ws-ref-here">
            <div class="ws-ref-here-val" style="color:{here_hue}">{result.here_score}</div>
            <div class="ws-ref-here-lbl">your spot</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Podium of all options
    cards = [_ref_card_html(o) for o in options]
    st.markdown(
        f'<div class="ws-ref-podium">{"".join(cards)}</div>',
        unsafe_allow_html=True,
    )

    # Heat matrix — destinations as columns, factors as rows
    n = len(options)
    cols = f"1.45fr repeat({n}, minmax(0,1fr))"
    parts = [f'<div class="ws-ref-matrix" style="grid-template-columns:{cols};">']
    parts.append('<div class="ws-ref-mcorner">Factor ↓ / Option →</div>')
    for o in options:
        wc = " is-top" if o.is_top else ""
        band_hue = _REF_BAND_HUE.get(o.band, o.band_color)
        # Trim long POI names for the matrix header.
        display_name = o.poi_name if len(o.poi_name) < 28 else o.poi_name[:25] + "…"
        parts.append(
            f'<div class="ws-ref-mhead{wc}" style="--hue:{band_hue};" '
            f'title="{_esc(o.poi_name)}">{_esc(display_name)}</div>'
        )

    # Headline refuge-score row
    parts.append('<div class="ws-ref-mlabel"><strong>Refuge score</strong></div>')
    for o in options:
        g = o.refuge_score / 100.0
        ch = _goodness_hue(g)
        parts.append(
            f'<div class="ws-ref-cell head-row" '
            f'style="background:{_hex_to_rgba(ch, 0.18)}; color:{ch};">'
            f'{o.refuge_score}</div>'
        )

    # Per-factor rows with weight chip
    from refuge import WEIGHTS as _REF_WEIGHTS  # avoid cycles for theme-only callers
    weight_lookup = {
        "proximity": _REF_WEIGHTS["proximity"],
        "path":      _REF_WEIGHTS["path"],
        "trust":     _REF_WEIGHTS["trust"],
        "open":      _REF_WEIGHTS["open"],
        "crowd":     _REF_WEIGHTS["crowd"],
    }
    for key, label in result.factor_order:
        w_pct = int(round(weight_lookup.get(key, 0.0) * 100))
        parts.append(
            f'<div class="ws-ref-mlabel">{_esc(label)}'
            f'<span class="ws-ref-mlabel-w">{w_pct}%</span></div>'
        )
        for o in options:
            f = next((ff for ff in o.factors if ff.key == key), None)
            if f is None:
                parts.append('<div class="ws-ref-cell">—</div>')
                continue
            ch = _goodness_hue(f.goodness)
            parts.append(
                f'<div class="ws-ref-cell" '
                f'style="background:{_hex_to_rgba(ch, 0.15)}; color:{ch};">'
                f'{_esc(f.display)}</div>'
            )
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)
    st.caption(
        "Greener = safer on that factor. Composite weights shown next to each row; corridor strip "
        "below each card shows path-safety across 5 sampled waypoints (dashed outline = inside a risk zone)."
    )

    # Emergency card + beacon
    _render_emergency_card(result.emergency_card)
    if result.quiet_beacon is not None:
        st.markdown(
            f"""
            <div class="ws-ref-beacon">
              <div class="ws-ref-beacon-title">📡 Quiet Beacon · ready to send</div>
              <div class="ws-ref-beacon-body">{_esc(result.quiet_beacon.payload_text)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_emergency_card(card) -> None:
    cells = "".join(
        f"""
        <div class="ws-ref-emergency-cell">
          <div class="ws-ref-emergency-num">{_esc(num)}</div>
          <div class="ws-ref-emergency-lbl">{_esc(lbl)}</div>
        </div>
        """
        for lbl, num in card.numbers
    )
    note_html = f'<div class="ws-ref-emergency-note">{_esc(card.note)}</div>' if card.note else ""
    st.markdown(
        f"""
        <div class="ws-ref-emergency">
          <div class="ws-ref-emergency-head">
            <span class="ws-ref-emergency-flag">{card.flag_emoji}</span>
            <span class="ws-ref-emergency-title">Emergency · {_esc(card.country)}</span>
          </div>
          <div class="ws-ref-emergency-grid">{cells}</div>
          {note_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_refuge_empty(hint: str = "Press **Find Refuge** above to scan for safe-haven options around you.") -> None:
    st.markdown(
        f"""
        <div class="ws-ref-empty">
          <div class="ws-ref-empty-title">Refuge engine idle</div>
          <div>{_esc(hint)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# Tempo — Departure-Window Optimizer (Day 51)
# ============================================================

_TEMPO_BAND_HUE = {
    "All-clear": "#53E3A6",
    "Caution":   "#F9C440",
    "Elevated":  "#FF9F43",
    "High Risk": "#FF7F50",
    "Danger":    "#FF3D60",
}

_TEMPO_FLAVOR_GLYPH = {
    "safest":   "🛡",
    "balanced": "⚖",
    "fastest":  "🏁",
}

_TEMPO_CSS = """
<style>
.ws-tempo-hero {
  position: relative;
  display: grid;
  grid-template-columns: 168px 1fr auto;
  gap: 18px;
  align-items: center;
  padding: 20px 22px;
  margin: 8px 0 16px 0;
  border-radius: 18px;
  background: linear-gradient(135deg, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0.01) 100%);
  border: 1px solid var(--hue, #3DA9FC);
  box-shadow: 0 6px 28px var(--glow, rgba(61,169,252,0.18));
}
.ws-tempo-ring {
  position: relative;
  width: 168px; height: 168px; border-radius: 50%;
  background:
    conic-gradient(var(--hue) calc(var(--pct,0) * 1%), rgba(255,255,255,0.06) 0);
  display: grid; place-items: center;
  box-shadow: 0 0 24px var(--glow, rgba(61,169,252,0.20));
}
.ws-tempo-ring::after {
  content: "";
  position: absolute; inset: 12px;
  border-radius: 50%;
  background: #0E1117;
}
.ws-tempo-ring-inner {
  position: relative; z-index: 1;
  display: grid; place-items: center;
  text-align: center;
}
.ws-tempo-ring-depart {
  font-size: 28px; font-weight: 800; color: #E6E9F2;
  letter-spacing: -0.02em; line-height: 1;
}
.ws-tempo-ring-rel {
  font-size: 11px; color: #8892A6; margin-top: 4px;
  text-transform: uppercase; letter-spacing: 0.06em;
}
.ws-tempo-ring-score {
  font-size: 12px; color: var(--hue); margin-top: 6px; font-weight: 700;
}
.ws-tempo-hero-body {
  display: flex; flex-direction: column; gap: 6px;
}
.ws-tempo-pill {
  align-self: flex-start;
  display: inline-flex; gap: 6px; align-items: center;
  padding: 3px 10px; border-radius: 999px;
  background: var(--pill-bg, rgba(61,169,252,0.14));
  border: 1px solid var(--hue, #3DA9FC);
  color: var(--hue, #3DA9FC);
  font-size: 11px; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.06em;
}
.ws-tempo-hero-title {
  font-size: 22px; font-weight: 800; color: #E6E9F2;
  letter-spacing: -0.01em; line-height: 1.25;
}
.ws-tempo-hero-detail { color: #C5CBDA; font-size: 14px; line-height: 1.45; }
.ws-tempo-hero-meta {
  display: flex; gap: 6px; flex-wrap: wrap; margin-top: 6px;
}
.ws-tempo-chip {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 2px 9px; border-radius: 999px;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.10);
  color: #C5CBDA; font-size: 11px; font-weight: 600;
  white-space: nowrap;
}
.ws-tempo-chip.warn {
  border-color: #FF7F50; color: #FF7F50;
  background: rgba(255,127,80,0.10);
}
.ws-tempo-arrival {
  display: grid; gap: 2px; text-align: right; min-width: 92px;
  padding-left: 14px; border-left: 1px dashed rgba(255,255,255,0.10);
}
.ws-tempo-arrival-val {
  font-size: 32px; font-weight: 800; color: #E6E9F2;
  letter-spacing: -0.02em; line-height: 1;
}
.ws-tempo-arrival-lbl {
  font-size: 10px; color: #8892A6;
  text-transform: uppercase; letter-spacing: 0.08em;
}

/* Heatmap grid */
.ws-tempo-grid-wrap {
  display: flex; flex-direction: column; gap: 6px;
  padding: 14px; border-radius: 16px;
  background: rgba(255,255,255,0.02);
  border: 1px solid rgba(255,255,255,0.06);
  margin-bottom: 16px;
}
.ws-tempo-grid-title {
  font-size: 12px; color: #8892A6; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.08em;
  margin-bottom: 4px;
}
.ws-tempo-grid {
  display: grid; gap: 6px;
  grid-template-columns: 92px repeat(var(--cols, 10), minmax(58px, 1fr));
  align-items: stretch;
}
.ws-tempo-h {
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; color: #8892A6; font-weight: 700;
  letter-spacing: 0.04em;
  height: 28px;
}
.ws-tempo-row-lbl {
  display: flex; flex-direction: column; justify-content: center;
  align-items: flex-start;
  padding: 6px 8px;
  font-size: 12px; font-weight: 700; color: #C5CBDA;
  border-radius: 8px;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.06);
}
.ws-tempo-row-lbl small { font-size: 10px; color: #8892A6; font-weight: 600; letter-spacing: 0.04em; }
.ws-tempo-cell {
  position: relative;
  display: grid; place-items: center;
  height: 56px; border-radius: 10px;
  background: var(--bg);
  border: 1px solid var(--bd);
  color: #E6E9F2;
  font-weight: 800; font-size: 15px;
  letter-spacing: -0.01em;
  cursor: default;
  transition: transform 0.12s ease;
}
.ws-tempo-cell:hover { transform: translateY(-1px); }
.ws-tempo-cell small {
  display: block; font-size: 9.5px; color: var(--accent, #E6E9F2);
  font-weight: 700; letter-spacing: 0.04em;
  margin-top: 2px; opacity: 0.85;
}
.ws-tempo-cell.win {
  outline: 2px solid var(--bd);
  outline-offset: 2px;
  box-shadow: 0 0 16px var(--glow, rgba(83,227,166,0.32));
}
.ws-tempo-cell.win::before {
  content: "★";
  position: absolute; top: 3px; right: 5px;
  font-size: 11px; color: var(--accent, #E6E9F2);
}
.ws-tempo-cell.dim {
  opacity: 0.32;
  background:
    repeating-linear-gradient(135deg,
      rgba(255,255,255,0.03) 0 6px,
      transparent 6px 12px),
    var(--bg);
}
.ws-tempo-legend {
  display: flex; gap: 14px; align-items: center; flex-wrap: wrap;
  margin-top: 8px; padding-top: 8px;
  border-top: 1px dashed rgba(255,255,255,0.08);
  font-size: 11px; color: #8892A6;
}
.ws-tempo-legend-swatch {
  display: inline-flex; align-items: center; gap: 5px;
}
.ws-tempo-legend-swatch i {
  width: 12px; height: 12px; border-radius: 3px; display: inline-block;
}

/* Comparison cards */
.ws-tempo-cmp-grid {
  display: grid; gap: 10px;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  margin: 8px 0 16px 0;
}
.ws-tempo-cmp {
  position: relative;
  display: flex; flex-direction: column; gap: 6px;
  padding: 14px;
  border-radius: 14px;
  background: rgba(255,255,255,0.025);
  border: 1px solid var(--bd, rgba(255,255,255,0.10));
}
.ws-tempo-cmp.win {
  background: linear-gradient(135deg, var(--glow, rgba(83,227,166,0.14)) 0%, rgba(255,255,255,0.025) 100%);
  border-color: var(--hue, #53E3A6);
}
.ws-tempo-cmp-label {
  font-size: 10px; color: #8892A6; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.08em;
}
.ws-tempo-cmp-times {
  font-size: 20px; font-weight: 800; color: #E6E9F2; letter-spacing: -0.01em;
}
.ws-tempo-cmp-times small {
  font-size: 11px; color: #8892A6; font-weight: 600; margin-left: 4px;
}
.ws-tempo-cmp-meta {
  display: flex; gap: 8px; flex-wrap: wrap;
  font-size: 11px; color: #C5CBDA;
}
.ws-tempo-cmp-meta span { white-space: nowrap; }
.ws-tempo-cmp-delta {
  margin-top: 4px;
  font-size: 12px; font-weight: 700;
}
.ws-tempo-cmp-delta.win { color: var(--hue, #53E3A6); }
.ws-tempo-cmp-delta.loss { color: #FF7F50; }
.ws-tempo-cmp-delta.flat { color: #8892A6; }
.ws-tempo-cmp-bar {
  height: 4px; border-radius: 999px;
  background: rgba(255,255,255,0.06);
  overflow: hidden;
  margin-top: 4px;
}
.ws-tempo-cmp-bar > i {
  display: block; height: 100%;
  background: var(--hue, #53E3A6);
  width: var(--pct, 0%);
}

/* Runners-up */
.ws-tempo-runners {
  display: grid; gap: 8px;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  margin: 4px 0 12px 0;
}
.ws-tempo-runner {
  display: flex; gap: 12px; align-items: center;
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(255,255,255,0.02);
  border: 1px solid rgba(255,255,255,0.08);
}
.ws-tempo-runner-rank {
  display: grid; place-items: center;
  width: 32px; height: 32px; border-radius: 50%;
  background: var(--bg, rgba(255,255,255,0.05));
  border: 1px solid var(--bd, rgba(255,255,255,0.18));
  color: var(--hue, #C5CBDA);
  font-weight: 800; font-size: 13px;
}
.ws-tempo-runner-body { flex: 1; display: flex; flex-direction: column; gap: 2px; }
.ws-tempo-runner-times { font-size: 14px; font-weight: 700; color: #E6E9F2; }
.ws-tempo-runner-meta { font-size: 11px; color: #8892A6; }

/* Rationale */
.ws-tempo-rationale {
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(83,227,166,0.06);
  border-left: 3px solid #53E3A6;
  margin-bottom: 14px;
}
.ws-tempo-rationale-title {
  font-size: 11px; color: #53E3A6; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.08em;
  margin-bottom: 6px;
}
.ws-tempo-rationale ul { margin: 0; padding-left: 18px; }
.ws-tempo-rationale li { color: #C5CBDA; font-size: 13px; line-height: 1.5; margin-bottom: 4px; }
.ws-tempo-rationale li:last-child { margin-bottom: 0; }

.ws-tempo-empty {
  padding: 28px 22px;
  border-radius: 16px;
  border: 1px dashed rgba(255,255,255,0.14);
  background: rgba(255,255,255,0.02);
  color: #C5CBDA;
  text-align: center;
}
.ws-tempo-empty-title { color: #E6E9F2; font-weight: 800; margin-bottom: 6px; }
.ws-tempo-empty small { color: #8892A6; }
</style>
"""


def _tempo_score_to_alpha(score: float) -> float:
    """Higher score → more saturated tint. Range ~0.10..0.34."""
    return 0.10 + 0.24 * max(0.0, min(1.0, score / 100.0))


def _tempo_relative(now, t) -> str:
    delta = int(round((t - now).total_seconds() / 60.0))
    if delta == 0:
        return "now"
    if delta > 0:
        if delta < 60:
            return f"in {delta} min"
        h, m = divmod(delta, 60)
        return f"in {h}h{m:02d}m" if m else f"in {h}h"
    delta = -delta
    if delta < 60:
        return f"{delta} min ago"
    h, m = divmod(delta, 60)
    return f"{h}h{m:02d}m ago" if m else f"{h}h ago"


def render_tempo(result) -> None:
    """Render the full Tempo result: hero card, heatmap grid, comparison cards,
    rationale, and runners-up."""
    st.markdown(_TEMPO_CSS, unsafe_allow_html=True)

    w = result.winner
    if w is None:
        st.markdown(
            """
            <div class="ws-tempo-empty">
              <div class="ws-tempo-empty-title">No feasible departure</div>
              <div>The arrival window is entirely in the past, or no route could be planned.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    hue = _TEMPO_BAND_HUE.get(w.band, w.band_color)
    glow = _hex_to_rgba(hue, 0.24)
    pill_bg = _hex_to_rgba(hue, 0.14)

    flavor_glyph = _TEMPO_FLAVOR_GLYPH.get(w.flavor, "🧭")

    fence_chip = ""
    if w.max_risk_segment_km >= 0.5:
        fence_chip = (
            f'<span class="ws-tempo-chip warn">'
            f'{w.max_risk_segment_km:.1f} km warm stretch'
            f'</span>'
        )

    feas_chip = ""
    if result.feasibility_note:
        feas_chip = (
            f'<span class="ws-tempo-chip warn">'
            f'{_esc(result.feasibility_note)}'
            f'</span>'
        )

    rel = _tempo_relative(result.now, w.depart)
    st.markdown(
        f"""
        <div class="ws-tempo-hero" style="--hue:{hue}; --glow:{glow};">
          <div class="ws-tempo-ring" style="--hue:{hue}; --pct:{w.composite}; --glow:{glow};">
            <div class="ws-tempo-ring-inner">
              <div class="ws-tempo-ring-depart">{w.depart.strftime('%H:%M')}</div>
              <div class="ws-tempo-ring-rel">{_esc(rel)}</div>
              <div class="ws-tempo-ring-score">{w.composite:.0f}/100 · {_esc(w.band)}</div>
            </div>
          </div>
          <div class="ws-tempo-hero-body">
            <span class="ws-tempo-pill" style="--hue:{hue}; --pill-bg:{pill_bg};">
              {flavor_glyph} {_esc(w.flavor)} · Tempo
            </span>
            <div class="ws-tempo-hero-title">{_rec_to_html(result.headline)}</div>
            <div class="ws-tempo-hero-detail">{_rec_to_html(result.advisory_line)}</div>
            <div class="ws-tempo-hero-meta">
              <span class="ws-tempo-chip">ETA {w.eta_minutes:.0f} min · {w.distance_km:.1f} km</span>
              <span class="ws-tempo-chip">risk-km {w.risk_km:.2f}</span>
              <span class="ws-tempo-chip">avg safety {w.avg_safety}</span>
              <span class="ws-tempo-chip">min {w.min_safety}</span>
              {fence_chip}
              {feas_chip}
            </div>
          </div>
          <div class="ws-tempo-arrival">
            <div class="ws-tempo-arrival-val">{w.arrival.strftime('%H:%M')}</div>
            <div class="ws-tempo-arrival-lbl">arrive · {_esc(result.dest_label)}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---------------- heatmap grid ----------------
    headers = "".join(
        f'<div class="ws-tempo-h">{s.strftime("%H:%M")}</div>'
        for s in result.arrival_slots
    )
    rows_html: list[str] = []
    for row in result.grid:
        if not row:
            continue
        flavor = row[0].flavor
        alpha_val = row[0].alpha
        glyph = _TEMPO_FLAVOR_GLYPH.get(flavor, "•")
        rows_html.append(
            f'<div class="ws-tempo-row-lbl">{glyph} {_esc(flavor)}'
            f'<small>α={alpha_val:g}</small></div>'
        )
        for c in row:
            cell_hue = _TEMPO_BAND_HUE.get(c.band, c.band_color)
            bg = _hex_to_rgba(cell_hue, _tempo_score_to_alpha(c.composite))
            bd = _hex_to_rgba(cell_hue, 0.42 if c.feasible else 0.20)
            classes = ["ws-tempo-cell"]
            if not c.feasible:
                classes.append("dim")
            is_win = (
                w is not None
                and c.arrival == w.arrival
                and c.alpha == w.alpha
            )
            cell_glow = ""
            if is_win:
                classes.append("win")
                cell_glow = f"--glow:{_hex_to_rgba(cell_hue, 0.42)};"
            cls_str = " ".join(classes)
            depart_hm = c.depart.strftime("%H:%M")
            arrival_hm = c.arrival.strftime("%H:%M")
            title_txt = (
                f"depart {depart_hm} · arrive {arrival_hm} · {flavor} · "
                f"composite {c.composite:.0f} · risk-km {c.risk_km:.2f}"
            )
            rows_html.append(
                f'<div class="{cls_str}" '
                f'style="--bg:{bg}; --bd:{bd}; --accent:{cell_hue}; {cell_glow}" '
                f'title="{title_txt}">'
                f'{c.composite:.0f}'
                f'<small>{depart_hm}</small>'
                f'</div>'
            )

    legend_items = "".join(
        f'<span class="ws-tempo-legend-swatch"><i style="background:{_hex_to_rgba(hex_, 0.55)};border:1px solid {hex_};"></i>{name}</span>'
        for name, hex_ in [
            ("All-clear", "#53E3A6"),
            ("Caution", "#F9C440"),
            ("Elevated", "#FF9F43"),
            ("High Risk", "#FF7F50"),
            ("Danger", "#FF3D60"),
        ]
    )

    st.markdown(
        f"""
        <div class="ws-tempo-grid-wrap">
          <div class="ws-tempo-grid-title">
            depart × arrival heatmap · {len(result.arrival_slots)} slots × {len(result.flavors)} flavors
            · step {result.step_min} min · ★ winner
          </div>
          <div class="ws-tempo-grid" style="--cols:{len(result.arrival_slots)};">
            <div class="ws-tempo-h"></div>
            {headers}
            {''.join(rows_html)}
          </div>
          <div class="ws-tempo-legend">
            {legend_items}
            <span style="margin-left:auto; color:#8892A6;">cells show composite · sub-label is depart-time</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---------------- comparison cards ----------------
    if result.comparisons:
        cmp_cards: list[str] = []
        max_delta = max((abs(cmp.delta_composite) for cmp in result.comparisons), default=1.0)
        max_delta = max(max_delta, 1.0)
        for cmp in result.comparisons:
            c = cmp.candidate
            if c is None:
                continue
            cell_hue = _TEMPO_BAND_HUE.get(c.band, c.band_color)
            bd = _hex_to_rgba(cell_hue, 0.32)
            cglow = _hex_to_rgba(cell_hue, 0.18)
            classes = ["ws-tempo-cmp"]
            delta_html: str
            bar_pct = 0
            if cmp.same_as_winner:
                classes.append("win")
                delta_html = (
                    f'<div class="ws-tempo-cmp-delta win">★ winner</div>'
                )
                bar_pct = 100
            else:
                if cmp.delta_composite > 0.5:
                    cls = "loss"
                    arrow = "▼"
                    txt = (
                        f"{arrow} −{cmp.delta_composite:.0f} pts · "
                        f"+{cmp.delta_risk_km:.2f} risk-km vs winner"
                    )
                elif cmp.delta_composite < -0.5:
                    cls = "win"
                    arrow = "▲"
                    txt = f"{arrow} +{-cmp.delta_composite:.0f} pts vs winner"
                else:
                    cls = "flat"
                    txt = "≈ tie with winner"
                delta_html = f'<div class="ws-tempo-cmp-delta {cls}">{txt}</div>'
                bar_pct = int(max(0, min(100, 100 * c.composite / 100.0)))
            cmp_cards.append(f"""
                <div class="{' '.join(classes)}" style="--hue:{cell_hue}; --bd:{bd}; --glow:{cglow};">
                  <div class="ws-tempo-cmp-label">{_esc(cmp.label)}</div>
                  <div class="ws-tempo-cmp-times">
                    {c.depart.strftime('%H:%M')} → {c.arrival.strftime('%H:%M')}
                    <small>{_esc(c.flavor)}</small>
                  </div>
                  <div class="ws-tempo-cmp-meta">
                    <span>composite <strong style="color:{cell_hue};">{c.composite:.0f}</strong></span>
                    <span>risk-km {c.risk_km:.2f}</span>
                    <span>ETA {c.eta_minutes:.0f}m</span>
                  </div>
                  <div class="ws-tempo-cmp-bar"><i style="--pct:{bar_pct}%; --hue:{cell_hue};"></i></div>
                  {delta_html}
                </div>
            """)
        st.markdown(
            f'<div class="ws-tempo-cmp-grid">{"".join(cmp_cards)}</div>',
            unsafe_allow_html=True,
        )

    # ---------------- rationale ----------------
    if result.rationale:
        items = "".join(f"<li>{_rec_to_html(r)}</li>" for r in result.rationale)
        st.markdown(
            f"""
            <div class="ws-tempo-rationale">
              <div class="ws-tempo-rationale-title">Why this minute</div>
              <ul>{items}</ul>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ---------------- runners-up ----------------
    if result.runners_up:
        runner_cards: list[str] = []
        for c in result.runners_up:
            cell_hue = _TEMPO_BAND_HUE.get(c.band, c.band_color)
            bg = _hex_to_rgba(cell_hue, 0.14)
            bd = _hex_to_rgba(cell_hue, 0.42)
            runner_cards.append(f"""
                <div class="ws-tempo-runner">
                  <div class="ws-tempo-runner-rank" style="--bg:{bg}; --bd:{bd}; --hue:{cell_hue};">
                    #{c.rank}
                  </div>
                  <div class="ws-tempo-runner-body">
                    <div class="ws-tempo-runner-times">
                      {c.depart.strftime('%H:%M')} → {c.arrival.strftime('%H:%M')}
                      · {_esc(c.flavor)}
                    </div>
                    <div class="ws-tempo-runner-meta">
                      composite <strong style="color:{cell_hue};">{c.composite:.0f}</strong>
                      · {_esc(c.band)}
                      · risk-km {c.risk_km:.2f}
                      · {c.distance_km:.1f} km
                    </div>
                  </div>
                </div>
            """)
        st.markdown(
            f"""
            <div style="margin-top:4px;">
              <div class="ws-tempo-grid-title">Runners-up (within 6 pts of winner)</div>
              <div class="ws-tempo-runners">{"".join(runner_cards)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_tempo_empty(hint: str = "Set an arrival window and press **Optimize Departure** to sweep the grid.") -> None:
    st.markdown(_TEMPO_CSS, unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="ws-tempo-empty">
          <div class="ws-tempo-empty-title">Tempo idle</div>
          <div>{_esc(hint)}</div>
          <small>Pure-Python optimisation over <code>plan_forecast_route</code> ×
          three route flavors × arrival-time slots. Picks the minute that minimises
          integrated forecast risk-distance on the actual corridor.</small>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================================
# Pulse — Today's Outlook brief (Day 56)
# ============================================================================

_PULSE_MOOD_HUE: dict[str, str] = {
    "Calm":     "#53E3A6",
    "Watch":    "#F9C440",
    "Active":   "#FF9F43",
    "Critical": "#FF3D60",
}

_PULSE_BAND_HUE: dict[str, str] = {
    "Safe":      "#53E3A6",
    "Caution":   "#F9C440",
    "High Risk": "#FF7F50",
    "Danger":    "#FF3D60",
    "Unknown":   "#8892A6",
}

_PULSE_CSS = """
<style>
.ws-pulse-hero {
  position:relative;
  border-radius:18px;
  padding:18px 22px;
  margin: 8px 0 14px;
  background:
    radial-gradient(140% 90% at -10% -40%, var(--glow) 0%, transparent 55%),
    linear-gradient(180deg, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0.01) 100%),
    #161A23;
  border: 1px solid rgba(255,255,255,0.08);
  display:grid;
  grid-template-columns: minmax(180px, 1fr) 3.4fr 1.3fr;
  gap: 18px;
  align-items:center;
  overflow:hidden;
}
.ws-pulse-hero::after {
  content:""; position:absolute; inset:0;
  background: linear-gradient(120deg, var(--glow) 0%, transparent 38%);
  pointer-events:none; opacity:.55;
}
.ws-pulse-pulse {
  width: 140px; height: 140px; border-radius: 50%;
  background: conic-gradient(var(--hue) calc(var(--pct) * 1%), rgba(255,255,255,0.07) 0);
  display:flex; align-items:center; justify-content:center;
  position:relative; box-shadow: 0 0 0 1px rgba(255,255,255,0.04), 0 0 40px var(--glow);
  flex-shrink:0;
}
.ws-pulse-pulse::after {
  content:""; position:absolute; inset:14px; border-radius:50%;
  background:#161A23; box-shadow: inset 0 0 0 1px rgba(255,255,255,0.05);
}
.ws-pulse-pulse-inner {
  position:relative; z-index:2;
  display:flex; flex-direction:column; align-items:center; gap:2px;
}
.ws-pulse-pulse-mood {
  font-size:.72rem; letter-spacing:.18em; text-transform:uppercase;
  color: var(--hue); font-weight:700;
}
.ws-pulse-pulse-score {
  font-variant-numeric:tabular-nums; font-weight:800;
  font-size: 1.95rem; letter-spacing:-.04em;
}
.ws-pulse-pulse-sub { font-size:.78rem; color:#A4ADC2; }
.ws-pulse-hero-body { position:relative; z-index:1; }
.ws-pulse-kicker {
  font-size:.72rem; letter-spacing:.22em; text-transform:uppercase;
  color: var(--hue); font-weight:700; margin-bottom:6px;
}
.ws-pulse-headline { font-size:1.32rem; font-weight:800; letter-spacing:-.02em; line-height:1.25; }
.ws-pulse-advisory { color:#C8D0E0; font-size:.95rem; margin-top:6px; }
.ws-pulse-mover {
  position:relative; z-index:1;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.07);
  border-radius:14px; padding:12px 14px;
  display:flex; flex-direction:column; gap:4px;
}
.ws-pulse-mover-kicker { color:#8892A6; font-size:.72rem; letter-spacing:.18em; text-transform:uppercase;}
.ws-pulse-mover-label { font-weight:700; font-size:1.0rem; }
.ws-pulse-mover-delta { font-weight:800; font-variant-numeric:tabular-nums;
  letter-spacing:-.02em; font-size:1.7rem; color: var(--mover-hue, #C8D0E0); }
.ws-pulse-mover-foot { color:#A4ADC2; font-size:.78rem; }

.ws-pulse-tiles {
  display:grid; grid-template-columns: repeat(4, 1fr); gap:10px; margin: 4px 0 16px;
}
.ws-pulse-tile {
  background: #161A23;
  border: 1px solid rgba(255,255,255,0.06);
  border-radius:12px;
  padding: 12px 14px;
  display:flex; flex-direction:column; gap:2px;
  position:relative; overflow:hidden;
}
.ws-pulse-tile::after {
  content:""; position:absolute; left:0; top:0; bottom:0; width:3px;
  background: var(--accent, #3DA9FC);
}
.ws-pulse-tile-kicker {
  color:#8892A6; font-size:.7rem; letter-spacing:.18em; text-transform:uppercase;
}
.ws-pulse-tile-val { font-weight:800; font-variant-numeric:tabular-nums;
  font-size:1.32rem; letter-spacing:-.02em; }
.ws-pulse-tile-sub { color:#A4ADC2; font-size:.78rem; }

.ws-pulse-ribbon-wrap {
  background:#161A23; border-radius:14px; padding:14px;
  border:1px solid rgba(255,255,255,0.06); margin-bottom:14px;
}
.ws-pulse-ribbon-title { font-weight:700; font-size:.94rem; margin-bottom:6px; }
.ws-pulse-ribbon-sub { color:#8892A6; font-size:.78rem; margin-bottom:10px; }
.ws-pulse-ribbon-grid {
  display:grid; grid-template-columns: 100px repeat(24, 1fr); gap:3px;
  align-items:end;
}
.ws-pulse-ribbon-label {
  font-size:.78rem; color:#C8D0E0; padding-right:6px; text-align:right;
  align-self:center; line-height:1.15;
}
.ws-pulse-ribbon-label small { display:block; color:#8892A6; font-size:.66rem; }
.ws-pulse-cell {
  height:38px; border-radius:5px; position:relative;
  background: linear-gradient(180deg, transparent 0%, transparent var(--top), var(--fill) var(--top));
  border:1px solid rgba(255,255,255,0.05);
  overflow:hidden;
}
.ws-pulse-cell.past { opacity:.35; }
.ws-pulse-cell.best { box-shadow: 0 0 0 1.5px #53E3A6, 0 0 12px rgba(83,227,166,0.45); }
.ws-pulse-cell.worst { box-shadow: 0 0 0 1.5px #FF3D60; }
.ws-pulse-cell.now-mark::after {
  content:""; position:absolute; left:50%; top:0; bottom:0; width:2px;
  background: rgba(61,169,252,0.8); box-shadow: 0 0 6px rgba(61,169,252,0.6);
}
.ws-pulse-hours {
  display:grid; grid-template-columns: 100px repeat(24, 1fr); gap:3px;
  color:#8892A6; font-size:.66rem; margin-top:6px;
}
.ws-pulse-hour { text-align:center; font-variant-numeric:tabular-nums; }
.ws-pulse-hour.best { color:#53E3A6; font-weight:700; }
.ws-pulse-hour.worst { color:#FF3D60; font-weight:700; }

.ws-pulse-snap {
  background: #161A23;
  border: 1px solid rgba(255,255,255,0.06);
  border-radius:14px;
  padding:14px 16px;
  display:grid;
  grid-template-columns: 100px 1.6fr 1fr;
  gap: 14px; align-items:center;
  margin-bottom: 10px;
  position:relative;
}
.ws-pulse-snap::before {
  content:""; position:absolute; left:0; top:14px; bottom:14px; width:3px;
  background: var(--accent, #8892A6); border-radius:0 4px 4px 0;
}
.ws-pulse-snap-ring {
  width: 78px; height:78px; border-radius:50%;
  background: conic-gradient(var(--hue) calc(var(--pct) * 1%), rgba(255,255,255,0.07) 0);
  display:flex; align-items:center; justify-content:center; position:relative;
}
.ws-pulse-snap-ring::after { content:""; position:absolute; inset:7px; border-radius:50%; background:#161A23; }
.ws-pulse-snap-ring-val { position:relative; z-index:2; font-weight:800; font-variant-numeric:tabular-nums; font-size:1.25rem; }
.ws-pulse-snap-title { display:flex; align-items:center; gap:6px; font-weight:700; font-size:1.02rem; letter-spacing:-.01em; }
.ws-pulse-snap-kind { color:#8892A6; font-size:.72rem; letter-spacing:.18em; text-transform:uppercase; }
.ws-pulse-chip {
  display:inline-block;
  padding:3px 8px; border-radius:999px;
  font-size:.72rem; font-weight:700;
  background: rgba(255,255,255,0.06);
  color:#E6EAF2;
  margin: 4px 4px 0 0;
}
.ws-pulse-chip.warn { background: rgba(255,159,67,0.16); color:#FFB077; }
.ws-pulse-chip.bad  { background: rgba(255,61,96,0.16);  color:#FF6F88; }
.ws-pulse-chip.ok   { background: rgba(83,227,166,0.14); color:#62E9B2; }
.ws-pulse-chip.delta-up   { background: rgba(83,227,166,0.16); color:#62E9B2; }
.ws-pulse-chip.delta-down { background: rgba(255,61,96,0.18);  color:#FF6F88; }
.ws-pulse-chip.delta-flat { background: rgba(255,255,255,0.06); color:#A4ADC2; }
.ws-pulse-snap-changes { color:#C8D0E0; font-size:.86rem; margin-top:6px; }
.ws-pulse-snap-changes b { color:#E6EAF2; }
.ws-pulse-snap-mini {
  display:grid; grid-template-columns: repeat(24, 1fr); gap:1px;
  height:18px; border-radius:4px; overflow:hidden;
}
.ws-pulse-snap-mini > i { background: var(--c, rgba(255,255,255,0.05)); display:block; }
.ws-pulse-snap-side {
  display:flex; flex-direction:column; gap:6px;
  font-size:.82rem; color:#C8D0E0;
}
.ws-pulse-snap-side b { color:#E6EAF2; }
.ws-pulse-snap-side small { color:#8892A6; }

.ws-pulse-section-title {
  font-weight:800; font-size:.92rem; letter-spacing:.04em; text-transform:uppercase;
  color:#8892A6; margin: 16px 0 6px;
}
.ws-pulse-list { list-style:none; padding-left:0; margin:0; }
.ws-pulse-list li {
  background:#161A23; border:1px solid rgba(255,255,255,0.06);
  border-radius:12px; padding:10px 14px; margin-bottom:6px;
  color:#E6EAF2; font-size:.94rem; line-height:1.4;
  position:relative; padding-left:36px;
}
.ws-pulse-list li::before {
  content: attr(data-i);
  position:absolute; left:10px; top:10px;
  width:20px; height:20px; border-radius:50%;
  background: rgba(255,255,255,0.08);
  font-size:.74rem; font-weight:700;
  display:flex; align-items:center; justify-content:center;
  color:#C8D0E0;
}
.ws-pulse-list li b { color:#E6EAF2; }
.ws-pulse-cluster-line {
  background:#161A23; border:1px solid rgba(255,255,255,0.06);
  border-radius:12px; padding:10px 14px; margin-bottom:6px;
  display:flex; align-items:center; gap:10px; font-size:.92rem;
}
.ws-pulse-cluster-dot { width:10px; height:10px; border-radius:50%; background: var(--hue); flex-shrink:0; }
.ws-pulse-empty {
  background: #161A23; border: 1px dashed rgba(255,255,255,0.10);
  border-radius:16px; padding: 26px; text-align:center;
  color:#A4ADC2;
}
.ws-pulse-empty-title { font-weight:800; color:#E6EAF2; font-size:1.05rem; margin-bottom:6px; }
</style>
"""


def _pulse_curve_to_cells(curve, *, now_hour: int, best_window=None, worst_window=None) -> str:
    """Render a 24-cell ribbon row for a single forecast curve.

    `curve` is 24 floats in [0,1]. `best_window` and `worst_window` are
    optional `(start, end_exclusive)` tuples — cells whose hour falls in the
    range get a coloured outline (best=green glow, worst=red ring).
    """
    cells: list[str] = []
    max_r = max(curve) if curve else 0.0
    for h in range(24):
        r = float(curve[h]) if h < len(curve) else 0.0
        # Map risk → color and fill height (top % from where the colored
        # band starts — small risk = mostly empty, high risk = tall bar).
        top_pct = max(8.0, 100.0 - r * 100.0)
        if r >= 0.66:
            hue = "#FF3D60"
        elif r >= 0.4:
            hue = "#FF7F50"
        elif r >= 0.2:
            hue = "#F9C440"
        else:
            hue = "#53E3A6"
        fill = _hex_to_rgba(hue, 0.42 + 0.45 * min(1.0, r))
        classes = ["ws-pulse-cell"]
        if h < now_hour:
            classes.append("past")
        if best_window is not None and _in_window(h, best_window):
            classes.append("best")
        if worst_window is not None and _in_window(h, worst_window):
            classes.append("worst")
        if h == now_hour:
            classes.append("now-mark")
        cls = " ".join(classes)
        title = f"{h:02d}:00 · risk {r:.2f}"
        cells.append(
            f'<div class="{cls}" '
            f'style="--top:{top_pct:.0f}%; --fill:{fill};" title="{title}"></div>'
        )
    return "".join(cells)


def _pulse_curve_to_mini(curve) -> str:
    """A compact 24-cell strip used inside per-snapshot cards."""
    parts: list[str] = []
    for h in range(24):
        r = float(curve[h]) if h < len(curve) else 0.0
        if r >= 0.66:
            hue = "#FF3D60"
        elif r >= 0.4:
            hue = "#FF7F50"
        elif r >= 0.2:
            hue = "#F9C440"
        else:
            hue = "#53E3A6"
        c = _hex_to_rgba(hue, 0.25 + 0.55 * min(1.0, r))
        parts.append(f'<i style="--c:{c};"></i>')
    return "".join(parts)


def _in_window(hour: int, window) -> bool:
    """Window is (start, end_exclusive) modulo 24."""
    start, end = int(window[0]), int(window[1])
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def _delta_chip(delta: int) -> str:
    if delta >= 5:
        cls = "delta-up"; arrow = "▲"
    elif delta <= -5:
        cls = "delta-down"; arrow = "▼"
    else:
        cls = "delta-flat"; arrow = "→"
    label = f"{arrow} {'+' if delta > 0 else ''}{delta} pts vs 24h ago"
    return f'<span class="ws-pulse-chip {cls}">{label}</span>'


def render_pulse(day) -> None:
    """Render the full Pulse — Today's Outlook brief."""
    st.markdown(_PULSE_CSS, unsafe_allow_html=True)

    hue = _PULSE_MOOD_HUE.get(day.overall_mood, "#8892A6")
    glow = _hex_to_rgba(hue, 0.20)

    overall_score = int(round(
        sum(s.score_now for s in day.snapshots) / max(1, len(day.snapshots))
    )) if day.snapshots else 0

    # ---------- hero ----------
    if day.biggest_mover is not None and abs(day.biggest_mover.delta_score) >= 1:
        bm = day.biggest_mover
        mover_hue = _PULSE_BAND_HUE.get(bm.band_now, "#C8D0E0")
        mover_block = f"""
          <div class="ws-pulse-mover">
            <div class="ws-pulse-mover-kicker">Biggest mover</div>
            <div class="ws-pulse-mover-label">{bm.point.glyph} {_esc(bm.point.label)}</div>
            <div class="ws-pulse-mover-delta" style="--mover-hue:{mover_hue};">
              {bm.delta_arrow} {bm.delta_label}
            </div>
            <div class="ws-pulse-mover-foot">
              {bm.band_24h_ago} → <b style="color:{mover_hue};">{bm.band_now}</b>
              · score {bm.score_now}
            </div>
          </div>
        """
    elif day.snapshots:
        # Calm day — show "no material change" tile in the mover slot.
        mover_block = """
          <div class="ws-pulse-mover">
            <div class="ws-pulse-mover-kicker">Day-over-day</div>
            <div class="ws-pulse-mover-label">No material change</div>
            <div class="ws-pulse-mover-delta delta-flat" style="--mover-hue:#A4ADC2;">→ ±0</div>
            <div class="ws-pulse-mover-foot">All watched points within ±5 pts of yesterday.</div>
          </div>
        """
    else:
        mover_block = ""

    st.markdown(
        f"""
        <div class="ws-pulse-hero" style="--hue:{hue}; --glow:{glow};">
          <div class="ws-pulse-pulse" style="--hue:{hue}; --pct:{overall_score}; --glow:{glow};">
            <div class="ws-pulse-pulse-inner">
              <div class="ws-pulse-pulse-mood">{_esc(day.overall_mood)}</div>
              <div class="ws-pulse-pulse-score">{overall_score}</div>
              <div class="ws-pulse-pulse-sub">mean score · {_esc(day.overall_band)}</div>
            </div>
          </div>
          <div class="ws-pulse-hero-body">
            <div class="ws-pulse-kicker">Today's outlook · {_esc(day.now.strftime('%a %d %b · %H:%M'))}</div>
            <div class="ws-pulse-headline">{_rec_to_html(day.headline)}</div>
            <div class="ws-pulse-advisory">{_rec_to_html(day.advisory_line)}</div>
          </div>
          {mover_block}
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---------- tiles ----------
    bw_s, bw_e = day.best_outdoor_window
    ww_s, ww_e = day.worst_outdoor_window
    overall_band_hue = _PULSE_BAND_HUE.get(day.overall_band, "#8892A6")

    new_inc_total = day.n_incidents_24h_total
    new_inc_hue = "#FF7F50" if new_inc_total >= 3 else ("#F9C440" if new_inc_total >= 1 else "#53E3A6")

    stay = next((s for s in day.snapshots if s.point.kind == "stay"), None)
    if stay is not None and stay.refuge_label:
        refuge_tile_val = stay.refuge_band
        refuge_tile_sub = f"{stay.refuge_label} · {stay.refuge_distance_km} km"
        refuge_hue = _PULSE_BAND_HUE.get(stay.refuge_band, "#8892A6")
    else:
        refuge_tile_val = "—"
        refuge_tile_sub = "no stay flagged"
        refuge_hue = "#8892A6"

    tiles_html = f"""
    <div class="ws-pulse-tiles">
      <div class="ws-pulse-tile" style="--accent:{overall_band_hue};">
        <div class="ws-pulse-tile-kicker">Overall band</div>
        <div class="ws-pulse-tile-val" style="color:{overall_band_hue};">{_esc(day.overall_band)}</div>
        <div class="ws-pulse-tile-sub">{len(day.snapshots)} watched · worst-of</div>
      </div>
      <div class="ws-pulse-tile" style="--accent:#53E3A6;">
        <div class="ws-pulse-tile-kicker">Best outdoor window</div>
        <div class="ws-pulse-tile-val">{bw_s:02d}:00–{bw_e:02d}:00</div>
        <div class="ws-pulse-tile-sub">joint risk {day.best_outdoor_window_risk:.2f}</div>
      </div>
      <div class="ws-pulse-tile" style="--accent:{new_inc_hue};">
        <div class="ws-pulse-tile-kicker">New incidents (24h, 1 km)</div>
        <div class="ws-pulse-tile-val" style="color:{new_inc_hue};">{new_inc_total}</div>
        <div class="ws-pulse-tile-sub">across {len(day.snapshots)} watched point{'s' if len(day.snapshots) != 1 else ''}</div>
      </div>
      <div class="ws-pulse-tile" style="--accent:{refuge_hue};">
        <div class="ws-pulse-tile-kicker">Refuge readiness · stay</div>
        <div class="ws-pulse-tile-val" style="color:{refuge_hue};">{_esc(refuge_tile_val)}</div>
        <div class="ws-pulse-tile-sub">{_esc(refuge_tile_sub)}</div>
      </div>
    </div>
    """
    st.markdown(tiles_html, unsafe_allow_html=True)

    # ---------- joint ribbon ----------
    now_hour = int(day.now.hour)
    joint_cells = _pulse_curve_to_cells(
        day.joint_curve, now_hour=now_hour,
        best_window=day.best_outdoor_window, worst_window=day.worst_outdoor_window,
    )
    hour_labels = []
    for h in range(24):
        cls = "ws-pulse-hour"
        if _in_window(h, day.best_outdoor_window): cls += " best"
        if _in_window(h, day.worst_outdoor_window): cls += " worst"
        hour_labels.append(f'<div class="{cls}">{h:02d}</div>')

    st.markdown(
        f"""
        <div class="ws-pulse-ribbon-wrap">
          <div class="ws-pulse-ribbon-title">Joint risk ribbon · today, max over watched points</div>
          <div class="ws-pulse-ribbon-sub">
            green outline = best 3-h window · red outline = avoid · blue line = now ({now_hour:02d}:00)
          </div>
          <div class="ws-pulse-ribbon-grid">
            <div class="ws-pulse-ribbon-label">Joint <small>max over watched</small></div>
            {joint_cells}
          </div>
          <div class="ws-pulse-hours">
            <div></div>
            {''.join(hour_labels)}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---------- per-snapshot cards ----------
    st.markdown('<div class="ws-pulse-section-title">Watched points</div>', unsafe_allow_html=True)
    for s in day.snapshots:
        band_hue = _PULSE_BAND_HUE.get(s.band_now, "#8892A6")
        delta_html = _delta_chip(s.delta_score)
        chips: list[str] = [delta_html]
        if s.new_incidents_24h:
            cat = f" · {s.dominant_new_category}" if s.dominant_new_category else ""
            chips.append(
                f'<span class="ws-pulse-chip warn">{s.new_incidents_24h} new (1 km, 24h){_esc(cat)}</span>'
            )
        for c in s.intersecting_clusters[:2]:
            cls = "bad" if c.is_escalating else ""
            chips.append(
                f'<span class="ws-pulse-chip {cls}">{_esc(c.label)} · {_esc(c.status_now)} '
                f'×{c.velocity:.1f} · {c.distance_km:.1f} km</span>'
            )
        if s.band_changed:
            chips.append(
                f'<span class="ws-pulse-chip warn">band {_esc(s.band_24h_ago)} → {_esc(s.band_now)}</span>'
            )
        chip_html = "".join(chips)

        changes_html = ""
        if s.changes:
            bullets = "".join(f"<div>· {_rec_to_html(c)}</div>" for c in s.changes)
            changes_html = f'<div class="ws-pulse-snap-changes">{bullets}</div>'

        side_lines = []
        side_lines.append(
            f'<div><small>best 3 h</small><br><b>'
            f'{s.best_window[0]:02d}:00–{s.best_window[1]:02d}:00</b> · risk {s.best_window_risk:.2f}</div>'
        )
        if s.refuge_label:
            side_lines.append(
                f'<div><small>nearest refuge</small><br><b>{_esc(s.refuge_label)}</b>'
                f' · {_esc(s.refuge_band)} · {s.refuge_distance_km} km</div>'
            )
        side_html = "".join(side_lines)

        mini = _pulse_curve_to_mini(s.hour_curve_today)

        st.markdown(
            f"""
            <div class="ws-pulse-snap" style="--accent:{band_hue};">
              <div>
                <div class="ws-pulse-snap-ring" style="--hue:{band_hue}; --pct:{s.score_now};">
                  <div class="ws-pulse-snap-ring-val">{s.score_now}</div>
                </div>
              </div>
              <div>
                <div class="ws-pulse-snap-kind">{_esc(s.point.kind)}</div>
                <div class="ws-pulse-snap-title">{s.point.glyph} {_esc(s.point.label)}
                  · <span style="color:{band_hue};">{_esc(s.band_now)}</span></div>
                <div>{chip_html}</div>
                {changes_html}
                <div style="margin-top:8px;">
                  <small style="color:#8892A6;">today's 24-h curve</small>
                  <div class="ws-pulse-snap-mini">{mini}</div>
                </div>
              </div>
              <div class="ws-pulse-snap-side">{side_html}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ---------- cluster intersections ----------
    if day.sentinel_intersections:
        st.markdown('<div class="ws-pulse-section-title">Sentinel intersections with your day</div>',
                    unsafe_allow_html=True)
        lines: list[str] = []
        for c in day.sentinel_intersections:
            hue = _cluster_status_hue(c.status_now)
            badge = (
                '<span class="ws-pulse-chip bad">escalating</span>'
                if c.is_escalating else ""
            )
            lines.append(
                f'<div class="ws-pulse-cluster-line">'
                f'<span class="ws-pulse-cluster-dot" style="--hue:{hue};"></span>'
                f'<div><b>{_esc(c.label)}</b> · {_esc(c.status_now)} ×{c.velocity:.1f}'
                f' · {c.recent_count} recent · edge {c.distance_km:.2f} km</div>'
                f'<div style="margin-left:auto;">{badge}</div>'
                f'</div>'
            )
        st.markdown("".join(lines), unsafe_allow_html=True)

    # ---------- change log ----------
    if day.change_log:
        st.markdown('<div class="ws-pulse-section-title">What changed since yesterday</div>',
                    unsafe_allow_html=True)
        items = "".join(
            f'<li data-i="{i+1}">{_rec_to_html(line)}</li>'
            for i, line in enumerate(day.change_log)
        )
        st.markdown(f'<ul class="ws-pulse-list">{items}</ul>', unsafe_allow_html=True)

    # ---------- plan of day ----------
    if day.actions:
        st.markdown('<div class="ws-pulse-section-title">Plan of day</div>', unsafe_allow_html=True)
        items = "".join(
            f'<li data-i="{i+1}">{_rec_to_html(a)}</li>'
            for i, a in enumerate(day.actions)
        )
        st.markdown(f'<ul class="ws-pulse-list">{items}</ul>', unsafe_allow_html=True)


def render_pulse_empty(hint: str = "Pick your stay and 1–3 destinations, then press **Compose Pulse**.") -> None:
    st.markdown(_PULSE_CSS, unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="ws-pulse-empty">
          <div class="ws-pulse-empty-title">Pulse idle</div>
          <div>{_esc(hint)}</div>
          <small style="color:#8892A6;">Pulse is a composer — it re-runs Safety,
          Forecast, Sentinel and Refuge for each watched point at <em>now</em>
          and at <em>now − 24 h</em>, then ranks the deltas into a single
          morning brief. Pure-Python, zero new deps.</small>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================================
# Beacon — Group Safety Coordinator (Day 61)
# ============================================================================

_BEACON_MOOD_HUE: dict[str, str] = {
    "Calm":     "#53E3A6",
    "Watch":    "#F9C440",
    "Active":   "#FF9F43",
    "Critical": "#FF3D60",
}

_BEACON_BAND_HUE: dict[str, str] = {
    "Safe":      "#53E3A6",
    "Caution":   "#F9C440",
    "High Risk": "#FF7F50",
    "Danger":    "#FF3D60",
    "Unknown":   "#8892A6",
}

_BEACON_SOURCE_HUE: dict[str, str] = {
    "help_poi":      "#3DA9FC",
    "centroid":      "#A78BFA",
    "safe_pocket":   "#53E3A6",
    "stable_member": "#F9C440",
}

_BEACON_SOURCE_LABEL: dict[str, str] = {
    "help_poi":      "help POI",
    "centroid":      "centroid",
    "safe_pocket":   "safe pocket",
    "stable_member": "stable member",
}

_BEACON_CSS = """
<style>
.ws-bcn-hero {
  position:relative;
  border-radius:18px;
  padding:18px 22px;
  margin: 8px 0 14px;
  background:
    radial-gradient(150% 95% at -8% -40%, var(--glow) 0%, transparent 55%),
    linear-gradient(180deg, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0.01) 100%),
    #161A23;
  border: 1px solid rgba(255,255,255,0.08);
  display:grid;
  grid-template-columns: minmax(190px, 1fr) 3.4fr 1.4fr;
  gap: 18px; align-items:center; overflow:hidden;
}
.ws-bcn-hero::after {
  content:""; position:absolute; inset:0;
  background: linear-gradient(120deg, var(--glow) 0%, transparent 38%);
  pointer-events:none; opacity:.55;
}
@keyframes ws-bcn-breathe {
  0%   { transform: scale(1.000); opacity:1.00; }
  50%  { transform: scale(1.028); opacity:0.88; }
  100% { transform: scale(1.000); opacity:1.00; }
}
.ws-bcn-ring {
  width: 152px; height: 152px; border-radius: 50%;
  background: conic-gradient(var(--hue) calc(var(--pct) * 1%), rgba(255,255,255,0.07) 0);
  display:flex; align-items:center; justify-content:center;
  position:relative; box-shadow: 0 0 0 1px rgba(255,255,255,0.04), 0 0 40px var(--glow);
  flex-shrink:0;
  animation: ws-bcn-breathe 4.6s ease-in-out infinite;
}
.ws-bcn-ring::after {
  content:""; position:absolute; inset:14px; border-radius:50%;
  background:#161A23; box-shadow: inset 0 0 0 1px rgba(255,255,255,0.05);
}
.ws-bcn-ring-inner {
  position:relative; z-index:2;
  display:flex; flex-direction:column; align-items:center; gap:2px;
}
.ws-bcn-ring-mood {
  font-size:.72rem; letter-spacing:.18em; text-transform:uppercase;
  color: var(--hue); font-weight:700;
}
.ws-bcn-ring-score {
  font-variant-numeric:tabular-nums; font-weight:800;
  font-size: 2.05rem; letter-spacing:-.04em;
}
.ws-bcn-ring-sub { font-size:.78rem; color:#A4ADC2; }
.ws-bcn-hero-body { position:relative; z-index:1; }
.ws-bcn-kicker {
  font-size:.72rem; letter-spacing:.22em; text-transform:uppercase;
  color: var(--hue); font-weight:700; margin-bottom:6px;
}
.ws-bcn-headline { font-size:1.32rem; font-weight:800; letter-spacing:-.02em; line-height:1.28; }
.ws-bcn-advisory { color:#C8D0E0; font-size:.95rem; margin-top:6px; }
.ws-bcn-concern {
  position:relative; z-index:1;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.07);
  border-radius:14px; padding:12px 14px;
  display:flex; flex-direction:column; gap:4px;
}
.ws-bcn-concern-kicker { color:#8892A6; font-size:.72rem; letter-spacing:.18em; text-transform:uppercase; }
.ws-bcn-concern-label { font-weight:700; font-size:1.0rem; }
.ws-bcn-concern-band {
  display:inline-block; align-self:flex-start;
  padding:3px 10px; border-radius:999px; font-weight:800;
  background: var(--bg, rgba(255,255,255,0.08)); color: var(--c, #E6EAF2);
  font-size:.78rem;
}
.ws-bcn-concern-sub { color:#A4ADC2; font-size:.78rem; }

.ws-bcn-tiles {
  display:grid; grid-template-columns: repeat(4, 1fr); gap:10px; margin: 4px 0 14px;
}
.ws-bcn-tile {
  background:#161A23; border:1px solid rgba(255,255,255,0.06);
  border-radius:12px; padding:12px 14px;
  display:flex; flex-direction:column; gap:2px;
  position:relative; overflow:hidden;
}
.ws-bcn-tile::after {
  content:""; position:absolute; left:0; top:0; bottom:0; width:3px;
  background: var(--accent, #3DA9FC);
}
.ws-bcn-tile-kicker { color:#8892A6; font-size:.7rem; letter-spacing:.18em; text-transform:uppercase; }
.ws-bcn-tile-val { font-weight:800; font-variant-numeric:tabular-nums;
  font-size:1.32rem; letter-spacing:-.02em; }
.ws-bcn-tile-sub { color:#A4ADC2; font-size:.78rem; }

.ws-bcn-section-title {
  font-weight:800; font-size:.92rem; letter-spacing:.04em; text-transform:uppercase;
  color:#8892A6; margin: 14px 0 6px;
}

.ws-bcn-member-grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap:10px; }
.ws-bcn-member {
  background:#161A23; border:1px solid rgba(255,255,255,0.06);
  border-radius:14px; padding:12px 14px;
  display:grid; grid-template-columns: 78px 1fr; gap:12px;
  align-items:center; position:relative;
}
.ws-bcn-member::before {
  content:""; position:absolute; left:0; top:14px; bottom:14px; width:3px;
  background: var(--accent, #8892A6); border-radius:0 4px 4px 0;
}
.ws-bcn-member-ring {
  width: 70px; height:70px; border-radius:50%;
  background: conic-gradient(var(--hue) calc(var(--pct) * 1%), rgba(255,255,255,0.07) 0);
  display:flex; align-items:center; justify-content:center; position:relative;
}
.ws-bcn-member-ring::after { content:""; position:absolute; inset:6px; border-radius:50%; background:#161A23; }
.ws-bcn-member-ring-val { position:relative; z-index:2; font-weight:800; font-variant-numeric:tabular-nums; font-size:1.15rem; }
.ws-bcn-member-name { font-weight:700; font-size:1.0rem; display:flex; align-items:center; gap:6px; }
.ws-bcn-member-kind { color:#8892A6; font-size:.7rem; letter-spacing:.18em; text-transform:uppercase; }
.ws-bcn-member-meta { display:flex; flex-wrap:wrap; gap:4px; margin-top:5px; }
.ws-bcn-chip {
  display:inline-block; padding:3px 8px; border-radius:999px;
  font-size:.72rem; font-weight:700;
  background: rgba(255,255,255,0.06); color:#E6EAF2;
}
.ws-bcn-chip.warn { background: rgba(255,159,67,0.16); color:#FFB077; }
.ws-bcn-chip.bad  { background: rgba(255,61,96,0.16);  color:#FF6F88; }
.ws-bcn-chip.ok   { background: rgba(83,227,166,0.14); color:#62E9B2; }
.ws-bcn-chip.cool { background: rgba(61,169,252,0.16); color:#7BC4FE; }

.ws-bcn-cand-table {
  background:#161A23; border:1px solid rgba(255,255,255,0.06);
  border-radius:14px; padding:8px;
}
.ws-bcn-cand-row {
  display:grid;
  grid-template-columns: 30px minmax(180px, 1.4fr) 64px 64px 80px 90px 80px;
  gap:8px; align-items:center;
  padding:8px 10px; border-bottom:1px solid rgba(255,255,255,0.04);
  font-size:.85rem;
}
.ws-bcn-cand-row:last-child { border-bottom: none; }
.ws-bcn-cand-row.head { color:#8892A6; font-size:.7rem; letter-spacing:.16em; text-transform:uppercase; border-bottom:1px solid rgba(255,255,255,0.08); }
.ws-bcn-cand-row.chosen {
  background: linear-gradient(180deg, rgba(83,227,166,0.06), rgba(83,227,166,0.02));
  border-left: 2px solid #53E3A6;
}
.ws-bcn-cand-row.secondary {
  background: linear-gradient(180deg, rgba(249,196,64,0.04), transparent);
  border-left: 2px solid rgba(249,196,64,0.6);
}
.ws-bcn-cand-rank {
  width:24px; height:24px; border-radius:50%;
  background: rgba(255,255,255,0.07); color:#C8D0E0;
  font-weight:700; font-size:.78rem;
  display:flex; align-items:center; justify-content:center;
}
.ws-bcn-cand-label { display:flex; flex-direction:column; gap:1px; }
.ws-bcn-cand-label b { font-size:.92rem; }
.ws-bcn-cand-label small { color:#8892A6; font-size:.7rem; letter-spacing:.18em; text-transform:uppercase; }
.ws-bcn-cand-num { font-variant-numeric:tabular-nums; font-weight:700; text-align:right; }
.ws-bcn-cand-score {
  font-variant-numeric:tabular-nums; font-weight:800;
  text-align:right;
}

.ws-bcn-alert {
  background:#161A23; border:1px solid rgba(255,255,255,0.06);
  border-radius:12px; padding:10px 14px; margin-bottom:6px;
  color:#E6EAF2; font-size:.94rem; line-height:1.4;
  border-left: 3px solid var(--severity, #F9C440);
}
.ws-bcn-alert b { color:#E6EAF2; }

.ws-bcn-plan-list { list-style:none; padding-left:0; margin:0; counter-reset: ws-bcn-plan; }
.ws-bcn-plan-list li {
  background:#161A23; border:1px solid rgba(255,255,255,0.06);
  border-radius:12px; padding:10px 14px 10px 40px; margin-bottom:6px;
  color:#E6EAF2; font-size:.94rem; line-height:1.45;
  position:relative;
}
.ws-bcn-plan-list li::before {
  counter-increment: ws-bcn-plan;
  content: counter(ws-bcn-plan);
  position:absolute; left:10px; top:10px;
  width:22px; height:22px; border-radius:50%;
  background: rgba(120, 200, 255, 0.16);
  color: #7BC4FE; font-size:.78rem; font-weight:800;
  display:flex; align-items:center; justify-content:center;
}
.ws-bcn-plan-list li b { color:#E6EAF2; }

.ws-bcn-source-pill {
  display:inline-block; padding:2px 8px; border-radius:999px;
  font-size:.66rem; font-weight:700; letter-spacing:.14em; text-transform:uppercase;
  background: var(--bg, rgba(255,255,255,0.06));
  color: var(--c, #C8D0E0);
}

.ws-bcn-empty {
  background:#161A23; border:1px dashed rgba(255,255,255,0.10);
  border-radius:16px; padding:26px; text-align:center; color:#A4ADC2;
}
.ws-bcn-empty-title { font-weight:800; color:#E6EAF2; font-size:1.05rem; margin-bottom:6px; }
</style>
"""


def _bcn_rec_to_html(text) -> str:
    """Tiny **bold** parser identical to the Pulse one."""
    if text is None:
        return ""
    s = _esc(str(text))
    out = []
    i = 0
    bold = False
    while i < len(s):
        if s[i] == "*" and i + 1 < len(s) and s[i + 1] == "*":
            out.append("</b>" if bold else "<b>")
            bold = not bold
            i += 2
        else:
            out.append(s[i]); i += 1
    if bold:
        out.append("</b>")
    return "".join(out).replace("\n", "<br/>")


def _bcn_alert_severity(line: str) -> str:
    low = line.lower()
    if "danger" in low or "critical" in low or "high risk" in low or "high_risk" in low:
        return "#FF3D60"
    if "isolated" in low or "fragmented" in low or "geofenced" in low:
        return "#FF9F43"
    if "corridor" in low or "re-route" in low or "escort" in low:
        return "#F9C440"
    return "#3DA9FC"


def render_beacon(report) -> None:
    """Render the full Beacon — Group Safety Coordinator brief."""
    st.markdown(_BEACON_CSS, unsafe_allow_html=True)

    mood = report.mood
    hue = _BEACON_MOOD_HUE.get(mood, "#8892A6")
    glow = _hex_to_rgba(hue, 0.22)

    # ---- hero ----------------------------------------------------------
    concern = next(
        (s for s in report.members if s.member.id == report.biggest_concern),
        None,
    )
    if concern is not None:
        c_hue = _BEACON_BAND_HUE.get(concern.band, "#C8D0E0")
        c_bg = _hex_to_rgba(c_hue, 0.18)
        concern_block = f"""
          <div class="ws-bcn-concern">
            <div class="ws-bcn-concern-kicker">Biggest concern</div>
            <div class="ws-bcn-concern-label">{_esc(concern.glyph)} {_esc(concern.member.label)}</div>
            <div class="ws-bcn-concern-band" style="--bg:{c_bg}; --c:{c_hue};">{_esc(concern.band)} · score {concern.score}</div>
            <div class="ws-bcn-concern-sub">
              isolation {concern.isolation_km:.2f} km · nearest help {(f'{concern.nearest_help_km:.2f} km' if concern.nearest_help_km is not None else '—')}
            </div>
          </div>
        """
    else:
        concern_block = ""

    st.markdown(
        f"""
        <div class="ws-bcn-hero" style="--hue:{hue}; --glow:{glow};">
          <div class="ws-bcn-ring" style="--hue:{hue}; --pct:{report.group_score}; --glow:{glow};">
            <div class="ws-bcn-ring-inner">
              <div class="ws-bcn-ring-mood">{_esc(mood)}</div>
              <div class="ws-bcn-ring-score">{report.group_score}</div>
              <div class="ws-bcn-ring-sub">group score · {_esc(report.group_band)}</div>
            </div>
          </div>
          <div class="ws-bcn-hero-body">
            <div class="ws-bcn-kicker">Beacon · {_esc(report.now.strftime('%a %d %b · %H:%M'))}</div>
            <div class="ws-bcn-headline">{_bcn_rec_to_html(report.headline)}</div>
            <div class="ws-bcn-advisory">{_bcn_rec_to_html(report.advisory_line)}</div>
          </div>
          {concern_block}
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---- 4-tile vital signs --------------------------------------------
    band_hue = _BEACON_BAND_HUE.get(report.group_band, "#8892A6")
    spread = report.group_spread_km
    if spread > 2.5:    spread_hue = "#FF3D60"
    elif spread > 1.2:  spread_hue = "#FF9F43"
    elif spread > 0.5:  spread_hue = "#F9C440"
    else:               spread_hue = "#53E3A6"
    chosen_lab = report.chosen.label if report.chosen else "—"
    chosen_eta = (
        f"{report.chosen.eta_max_minutes:.0f} min slow · {report.chosen.max_walk_km:.2f} km"
        if report.chosen else "no candidate"
    )
    chosen_src_hue = _BEACON_SOURCE_HUE.get(report.chosen.source, "#8892A6") if report.chosen else "#8892A6"
    st.markdown(
        f"""
        <div class="ws-bcn-tiles">
          <div class="ws-bcn-tile" style="--accent:{band_hue};">
            <div class="ws-bcn-tile-kicker">Group band</div>
            <div class="ws-bcn-tile-val" style="color:{band_hue};">{_esc(report.group_band)}</div>
            <div class="ws-bcn-tile-sub">score {report.group_score} · {len(report.members)} member(s)</div>
          </div>
          <div class="ws-bcn-tile" style="--accent:{spread_hue};">
            <div class="ws-bcn-tile-kicker">Group spread</div>
            <div class="ws-bcn-tile-val" style="color:{spread_hue};">{spread:.2f} km</div>
            <div class="ws-bcn-tile-sub">max pairwise distance</div>
          </div>
          <div class="ws-bcn-tile" style="--accent:#A78BFA;">
            <div class="ws-bcn-tile-kicker">Mood</div>
            <div class="ws-bcn-tile-val" style="color:{hue};">{_esc(mood)}</div>
            <div class="ws-bcn-tile-sub">{len(report.alerts)} alert(s) · {len(report.candidates)} candidate(s)</div>
          </div>
          <div class="ws-bcn-tile" style="--accent:{chosen_src_hue};">
            <div class="ws-bcn-tile-kicker">Meet at</div>
            <div class="ws-bcn-tile-val">{_esc(chosen_lab[:22])}</div>
            <div class="ws-bcn-tile-sub">{_esc(chosen_eta)}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---- Per-member cards ----------------------------------------------
    st.markdown('<div class="ws-bcn-section-title">Members</div>', unsafe_allow_html=True)
    cor_by_id = {c.member_id: c for c in report.corridors}
    cards: list[str] = []
    for s in report.members:
        m_hue = _BEACON_BAND_HUE.get(s.band, "#8892A6")
        cor = cor_by_id.get(s.member.id)
        chips: list[str] = []
        chips.append(f'<span class="ws-bcn-chip">iso {s.isolation_km:.2f} km</span>')
        if s.nearest_help_km is not None:
            help_cls = "ok" if s.nearest_help_km <= 1.0 else ("warn" if s.nearest_help_km <= 2.5 else "bad")
            chips.append(f'<span class="ws-bcn-chip {help_cls}">help {s.nearest_help_km:.2f} km</span>')
        if cor is not None:
            cor_cls = "bad" if cor.peak_risk >= 0.55 else ("warn" if cor.peak_risk >= 0.35 else "ok")
            chips.append(f'<span class="ws-bcn-chip {cor_cls}">→ meet · {cor.distance_km:.2f} km · {cor.eta_minutes:.0f} min</span>')
            chips.append(f'<span class="ws-bcn-chip {cor_cls}">corridor risk {cor.peak_risk:.2f}</span>')
        band_cls = {"Safe": "ok", "Caution": "warn", "High Risk": "bad", "Danger": "bad"}.get(s.band, "")
        chips.append(f'<span class="ws-bcn-chip {band_cls}">{_esc(s.band)}</span>')
        chips_html = "".join(chips)
        cards.append(f"""
          <div class="ws-bcn-member" style="--accent:{m_hue};">
            <div class="ws-bcn-member-ring" style="--hue:{m_hue}; --pct:{s.score};">
              <div class="ws-bcn-member-ring-val">{s.score}</div>
            </div>
            <div>
              <div class="ws-bcn-member-name">{_esc(s.glyph)} {_esc(s.member.label)}</div>
              <div class="ws-bcn-member-kind">{_esc(s.member.kind)}</div>
              <div class="ws-bcn-member-meta">{chips_html}</div>
            </div>
          </div>
        """)
    st.markdown(
        f'<div class="ws-bcn-member-grid">{"".join(cards)}</div>',
        unsafe_allow_html=True,
    )

    # ---- Meet-point candidates -----------------------------------------
    if report.candidates:
        st.markdown('<div class="ws-bcn-section-title">Meet-point candidates</div>', unsafe_allow_html=True)
        rows: list[str] = []
        rows.append("""
          <div class="ws-bcn-cand-row head">
            <div></div>
            <div>Where</div>
            <div style="text-align:right;">Score</div>
            <div style="text-align:right;">Safety</div>
            <div style="text-align:right;">Max walk</div>
            <div style="text-align:right;">Sum walk</div>
            <div style="text-align:right;">Worst risk</div>
          </div>
        """)
        chosen_id = id(report.chosen) if report.chosen else None
        secondary_id = id(report.secondary) if report.secondary else None
        for i, c in enumerate(report.candidates[:6], 1):
            extra_cls = ""
            if id(c) == chosen_id:
                extra_cls = " chosen"
            elif id(c) == secondary_id:
                extra_cls = " secondary"
            src_hue = _BEACON_SOURCE_HUE.get(c.source, "#8892A6")
            src_bg = _hex_to_rgba(src_hue, 0.16)
            src_label = _BEACON_SOURCE_LABEL.get(c.source, c.source)
            risk_hue = "#FF3D60" if c.max_path_risk >= 0.55 else ("#F9C440" if c.max_path_risk >= 0.35 else "#53E3A6")
            rows.append(f"""
              <div class="ws-bcn-cand-row{extra_cls}">
                <div class="ws-bcn-cand-rank">{i}</div>
                <div class="ws-bcn-cand-label">
                  <b>{_esc(c.label)}</b>
                  <small><span class="ws-bcn-source-pill" style="--bg:{src_bg}; --c:{src_hue};">{_esc(src_label)}</span></small>
                </div>
                <div class="ws-bcn-cand-score" style="color:{_BEACON_MOOD_HUE.get(mood) if id(c)==chosen_id else '#E6EAF2'};">{c.score}</div>
                <div class="ws-bcn-cand-num">{c.safety_at}</div>
                <div class="ws-bcn-cand-num">{c.max_walk_km:.2f} km</div>
                <div class="ws-bcn-cand-num">{c.sum_walk_km:.2f} km</div>
                <div class="ws-bcn-cand-num" style="color:{risk_hue};">{c.max_path_risk:.2f}</div>
              </div>
            """)
        st.markdown(
            f'<div class="ws-bcn-cand-table">{"".join(rows)}</div>',
            unsafe_allow_html=True,
        )

    # ---- Alerts --------------------------------------------------------
    if report.alerts:
        st.markdown('<div class="ws-bcn-section-title">Alerts</div>', unsafe_allow_html=True)
        for line in report.alerts:
            sev = _bcn_alert_severity(line)
            st.markdown(
                f'<div class="ws-bcn-alert" style="--severity:{sev};">{_bcn_rec_to_html(line)}</div>',
                unsafe_allow_html=True,
            )

    # ---- Plan of action ------------------------------------------------
    if report.plan_of_action:
        st.markdown('<div class="ws-bcn-section-title">Plan of action</div>', unsafe_allow_html=True)
        items = "".join(
            f'<li>{_bcn_rec_to_html(p)}</li>' for p in report.plan_of_action
        )
        st.markdown(f'<ol class="ws-bcn-plan-list">{items}</ol>', unsafe_allow_html=True)


def render_beacon_empty(
    hint: str = "Add 2–6 group members (lat/lon), then press **Compose Beacon**.",
) -> None:
    st.markdown(_BEACON_CSS, unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="ws-bcn-empty">
          <div class="ws-bcn-empty-title">Beacon idle</div>
          <div>{_esc(hint)}</div>
          <small style="color:#8892A6;">Beacon is a *group-first* composer —
          every other WaySafe surface scores a single point at a time.
          Beacon scores the group as a whole, ranks meet-point candidates by
          how the walk to each point would actually go for every member, and
          paints rendezvous corridors with per-waypoint risk samples.
          Pure-Python, zero new deps.</small>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ===================================================================
# Echo — Post-Trip Debrief (Day 66)
# ===================================================================

_ECHO_BAND_HUE = {
    "All-clear": "#53E3A6",
    "Caution":   "#F9C440",
    "Elevated":  "#FF9F43",
    "High Risk": "#FF7F50",
    "Danger":    "#FF3D60",
}

_ECHO_MOOD_HUE = {
    "Smooth":   "#53E3A6",
    "Watch":    "#F9C440",
    "Rough":    "#FF7F50",
    "Critical": "#FF3D60",
}

_ECHO_MOOD_GLYPH = {
    "Smooth":   "🟢",
    "Watch":    "🟡",
    "Rough":    "🟠",
    "Critical": "🔴",
}

_ECHO_CALIB_HUE = {
    "Sharp": "#53E3A6",
    "OK":    "#9FD3FF",
    "Noisy": "#F9C440",
    "Off":   "#FF7F50",
}

_ECHO_SCENARIO_GLYPH = {
    "actual":           "🛣",
    "fastest":          "🏁",
    "safest":           "🛡",
    "forecast-safest":  "🔮",
}

_ECHO_CSS = """
<style>
.ws-echo-hero {
  position: relative;
  display: grid;
  grid-template-columns: 178px 1fr auto;
  gap: 22px;
  align-items: center;
  padding: 22px 24px;
  margin: 8px 0 18px 0;
  border-radius: 20px;
  background:
    radial-gradient(ellipse 60% 70% at 18% 10%, var(--glow), transparent 70%),
    linear-gradient(135deg, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0.01) 100%);
  border: 1px solid var(--hue, #3DA9FC);
  box-shadow: 0 10px 36px var(--glow, rgba(61,169,252,0.20));
}
.ws-echo-ring {
  position: relative;
  width: 178px; height: 178px; border-radius: 50%;
  background:
    conic-gradient(var(--hue) calc(var(--pct,0) * 1%), rgba(255,255,255,0.06) 0);
  display: grid; place-items: center;
  box-shadow: 0 0 30px var(--glow, rgba(61,169,252,0.22));
}
.ws-echo-ring::after {
  content: "";
  position: absolute; inset: 12px;
  border-radius: 50%;
  background: #0E1117;
}
.ws-echo-ring-inner {
  position: relative; z-index: 1;
  display: grid; place-items: center;
  text-align: center;
}
.ws-echo-ring-score {
  font-size: 36px; font-weight: 800; color: #E6E9F2;
  letter-spacing: -0.02em; line-height: 1;
}
.ws-echo-ring-of100 {
  font-size: 11px; color: #8892A6; margin-top: 4px;
  text-transform: uppercase; letter-spacing: 0.10em;
}
.ws-echo-ring-band {
  font-size: 12px; color: var(--hue); margin-top: 6px; font-weight: 700;
}
.ws-echo-hero-body { display: flex; flex-direction: column; gap: 6px; }
.ws-echo-pill {
  align-self: flex-start;
  display: inline-flex; gap: 8px; align-items: center;
  padding: 4px 12px; border-radius: 999px;
  background: var(--pill-bg, rgba(61,169,252,0.14));
  border: 1px solid var(--hue, #3DA9FC);
  color: var(--hue, #3DA9FC);
  font-size: 11px; font-weight: 800;
  text-transform: uppercase; letter-spacing: 0.08em;
}
.ws-echo-hero-title {
  font-size: 22px; font-weight: 800; color: #E6E9F2;
  letter-spacing: -0.01em; line-height: 1.25;
}
.ws-echo-hero-detail { color: #C5CBDA; font-size: 14px; line-height: 1.5; }
.ws-echo-hero-meta {
  display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px;
}
.ws-echo-chip {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 2px 10px; border-radius: 999px;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.10);
  color: #C5CBDA; font-size: 11px; font-weight: 700;
}
.ws-echo-chip.warn { color: #F9C440; border-color: rgba(249,196,64,0.35); }
.ws-echo-chip.bad  { color: #FF7F50; border-color: rgba(255,127,80,0.35); }
.ws-echo-chip.crit { color: #FF3D60; border-color: rgba(255,61,96,0.40); }
.ws-echo-chip.good { color: #53E3A6; border-color: rgba(83,227,166,0.35); }
.ws-echo-mood {
  text-align: right;
  padding: 10px 14px;
  border-radius: 14px;
  background: var(--mood-bg);
  border: 1px solid var(--mood-hue);
  color: var(--mood-hue);
  min-width: 110px;
}
.ws-echo-mood-glyph { font-size: 26px; line-height: 1; }
.ws-echo-mood-label {
  font-size: 11px; font-weight: 800; margin-top: 4px;
  letter-spacing: 0.10em; text-transform: uppercase;
}
.ws-echo-mood-mini  { font-size: 10px; color: #8892A6; margin-top: 4px; }

/* ----- 4-tile factor strip ----- */
.ws-echo-factors {
  display: grid; grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin: 6px 0 18px 0;
}
.ws-echo-factor {
  position: relative;
  padding: 12px 14px;
  border-radius: 12px;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.08);
  box-shadow: inset 4px 0 0 0 var(--rim);
}
.ws-echo-factor-label {
  font-size: 10px; color: #8892A6;
  text-transform: uppercase; letter-spacing: 0.08em;
}
.ws-echo-factor-value {
  font-size: 26px; font-weight: 800; color: #E6E9F2;
  letter-spacing: -0.02em; margin-top: 2px;
}
.ws-echo-factor-small { font-size: 11px; color: #9FA6BB; margin-top: 2px; }
.ws-echo-factor-detail { font-size: 11px; color: #6F7790; margin-top: 6px; }

/* ----- corridor strip ----- */
.ws-echo-corridor {
  display: flex;
  height: 32px;
  width: 100%;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid rgba(255,255,255,0.08);
  background: rgba(255,255,255,0.02);
}
.ws-echo-corridor-cell {
  flex: 1;
  position: relative;
  background: var(--bg);
  border-right: 1px solid rgba(0,0,0,0.20);
}
.ws-echo-corridor-cell.fence::after {
  content: "";
  position: absolute; inset: 0;
  background-image: repeating-linear-gradient(
    45deg,
    transparent 0 2px,
    rgba(0,0,0,0.30) 2px 4px
  );
}
.ws-echo-corridor-legend {
  display: flex;
  justify-content: space-between;
  font-size: 10px; color: #8892A6;
  margin: 4px 2px 0 2px;
  text-transform: uppercase; letter-spacing: 0.08em;
}

/* ----- timeline ----- */
.ws-echo-timeline {
  display: flex; flex-direction: column; gap: 6px;
  margin: 6px 0;
}
.ws-echo-tl-row {
  display: grid; grid-template-columns: 80px 28px 1fr auto;
  gap: 10px; align-items: center;
  padding: 8px 12px; border-radius: 10px;
  background: rgba(255,255,255,0.025);
  border-left: 3px solid var(--accent, #9FD3FF);
  border-right: 1px solid rgba(255,255,255,0.06);
  border-top: 1px solid rgba(255,255,255,0.06);
  border-bottom: 1px solid rgba(255,255,255,0.06);
}
.ws-echo-tl-ts { color: #8892A6; font-family: ui-monospace, monospace; font-size: 11px; }
.ws-echo-tl-icon { font-size: 16px; text-align: center; }
.ws-echo-tl-msg { color: #E6E9F2; font-size: 13px; line-height: 1.4; }
.ws-echo-tl-msg .kind { color: var(--accent, #9FD3FF); font-weight: 700; font-size: 11px; margin-right: 6px; text-transform: uppercase; letter-spacing: 0.06em; }
.ws-echo-tl-km { color: #8892A6; font-size: 10px; font-family: ui-monospace, monospace; }

/* ----- counterfactual cards ----- */
.ws-echo-cf-grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px;
  margin: 8px 0 12px 0;
}
.ws-echo-cf {
  position: relative;
  padding: 14px 16px;
  border-radius: 14px;
  background: rgba(255,255,255,0.03);
  border: 1px solid var(--hue, #3DA9FC);
  box-shadow: 0 4px 14px var(--glow, rgba(61,169,252,0.10));
}
.ws-echo-cf.win {
  background:
    radial-gradient(circle at 0% 0%, var(--glow), transparent 60%),
    rgba(255,255,255,0.04);
  box-shadow: 0 6px 24px var(--glow);
}
.ws-echo-cf-head { display: flex; align-items: center; gap: 8px; }
.ws-echo-cf-glyph { font-size: 20px; }
.ws-echo-cf-label {
  font-size: 12px; font-weight: 800; color: var(--hue);
  text-transform: uppercase; letter-spacing: 0.06em;
}
.ws-echo-cf-pill {
  margin-left: auto;
  font-size: 10px; padding: 1px 8px; border-radius: 999px;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.10);
  color: #9FA6BB;
}
.ws-echo-cf-score {
  font-size: 28px; font-weight: 800; color: #E6E9F2;
  letter-spacing: -0.02em; margin-top: 6px; line-height: 1;
}
.ws-echo-cf-band { font-size: 11px; color: var(--hue); font-weight: 700; }
.ws-echo-cf-stat {
  display: flex; justify-content: space-between;
  font-size: 11px; color: #C5CBDA;
  margin-top: 4px;
}
.ws-echo-cf-delta {
  margin-top: 8px;
  padding: 6px 8px;
  border-radius: 8px;
  background: rgba(255,255,255,0.025);
  font-size: 11px; color: #9FA6BB;
  display: grid; grid-template-columns: repeat(2, 1fr); gap: 4px;
}
.ws-echo-cf-delta b { color: #E6E9F2; }
.ws-echo-cf-delta .pos { color: #53E3A6; }
.ws-echo-cf-delta .neg { color: #FF7F50; }

/* ----- calibration block ----- */
.ws-echo-calib {
  display: grid; grid-template-columns: 88px 1fr;
  gap: 14px;
  padding: 14px 16px;
  margin: 8px 0;
  border-radius: 14px;
  background: rgba(255,255,255,0.03);
  border: 1px solid var(--hue, #9FD3FF);
}
.ws-echo-calib-dial {
  display: grid; place-items: center;
  width: 88px; height: 88px;
  border-radius: 50%;
  background: conic-gradient(var(--hue) calc(var(--pct,0) * 1%), rgba(255,255,255,0.06) 0);
  position: relative;
}
.ws-echo-calib-dial::after {
  content: "";
  position: absolute; inset: 8px;
  border-radius: 50%;
  background: #0E1117;
}
.ws-echo-calib-dial-inner {
  position: relative; z-index: 1; text-align: center;
}
.ws-echo-calib-band { font-size: 13px; font-weight: 800; color: var(--hue); }
.ws-echo-calib-brier { font-size: 10px; color: #8892A6; margin-top: 2px; }
.ws-echo-calib-body { display: flex; flex-direction: column; gap: 6px; }
.ws-echo-calib-stat-row { display: flex; gap: 6px; flex-wrap: wrap; }
.ws-echo-calib-stat {
  font-size: 11px;
  padding: 2px 9px; border-radius: 999px;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.10);
  color: #C5CBDA;
}
.ws-echo-calib-stat.pos { color: #53E3A6; border-color: rgba(83,227,166,0.35); }
.ws-echo-calib-stat.neg { color: #FF7F50; border-color: rgba(255,127,80,0.35); }
.ws-echo-calib-stat.miss { color: #FF3D60; border-color: rgba(255,61,96,0.40); }
.ws-echo-calib-summary { color: #C5CBDA; font-size: 13px; line-height: 1.45; }

/* ----- lessons list ----- */
.ws-echo-lessons {
  display: flex; flex-direction: column; gap: 6px;
  margin: 4px 0;
}
.ws-echo-lesson {
  padding: 9px 14px;
  border-radius: 10px;
  background: rgba(255,255,255,0.025);
  border-left: 3px solid #9FD3FF;
  color: #E6E9F2;
  font-size: 13px;
  line-height: 1.45;
}
.ws-echo-lesson.prio { border-left-color: #FF7F50; }
.ws-echo-lesson.crit { border-left-color: #FF3D60; }
.ws-echo-lesson.good { border-left-color: #53E3A6; }

/* ----- empty card ----- */
.ws-echo-empty {
  padding: 22px;
  border-radius: 16px;
  background: linear-gradient(135deg, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0.01) 100%);
  border: 1px solid rgba(159,211,255,0.30);
  color: #C5CBDA;
}
.ws-echo-empty-title { color: #E6E9F2; font-weight: 800; font-size: 16px; margin-bottom: 4px; }
.ws-echo-section-title {
  color: #E6E9F2; font-weight: 800; font-size: 13px;
  text-transform: uppercase; letter-spacing: 0.08em;
  margin: 18px 0 8px 0;
}
.ws-echo-section-sub { color: #8892A6; font-size: 11px; margin-bottom: 6px; }
</style>
"""


def _echo_risk_hue(risk: float) -> str:
    """Map 0..1 risk to a corridor cell hue (greener = safer)."""
    risk = max(0.0, min(1.0, risk))
    if risk < 0.18:  return "#53E3A6"
    if risk < 0.32:  return "#9FD3FF"
    if risk < 0.45:  return "#F9C440"
    if risk < 0.60:  return "#FF9F43"
    if risk < 0.75:  return "#FF7F50"
    return "#FF3D60"


def _echo_rec_to_html(text: str) -> str:
    """Same minimal **bold** parser used everywhere — copy of _rec_to_html
    behaviour with HTML-escape on the surrounding text."""
    if text is None:
        return ""
    import re
    parts = re.split(r"(\*\*[^*]+\*\*)", str(text))
    out = []
    for p in parts:
        if p.startswith("**") and p.endswith("**"):
            out.append(f"<b>{_esc(p[2:-2])}</b>")
        else:
            out.append(_esc(p))
    return "".join(out)


def render_echo(report) -> None:
    """Render the full Echo debrief: hero ring + mood, factor strip,
    corridor heat strip, counterfactual cards, calibration, event
    timeline, lessons. Pure HTML/CSS — no streamlit charts."""
    st.markdown(_ECHO_CSS, unsafe_allow_html=True)

    hue = _ECHO_BAND_HUE.get(report.band, report.band_color)
    glow = _hex_to_rgba(hue, 0.22)
    pill_bg = _hex_to_rgba(hue, 0.14)
    mood_hue = _ECHO_MOOD_HUE.get(report.mood, "#9FD3FF")
    mood_bg = _hex_to_rgba(mood_hue, 0.14)
    mood_glyph = _ECHO_MOOD_GLYPH.get(report.mood, "•")

    # ---- meta chips on the hero ----
    chip_html: list[str] = []
    chip_html.append(
        f'<span class="ws-echo-chip">'
        f'{_esc(report.route_mode)}</span>'
    )
    chip_html.append(
        f'<span class="ws-echo-chip">'
        f'{report.distance_km:.1f} km · '
        f'{int(report.duration_min)} min</span>'
    )
    chip_html.append(
        f'<span class="ws-echo-chip">risk-km '
        f'{report.risk_km:.2f}</span>'
    )
    if report.geofence_minutes >= 1.0:
        chip_html.append(
            f'<span class="ws-echo-chip warn">{report.geofence_minutes:.0f} min '
            f'inside fence</span>'
        )
    if report.n_critical_alerts >= 1:
        chip_html.append(
            f'<span class="ws-echo-chip crit">{report.n_critical_alerts} critical '
            f'alert(s)</span>'
        )
    if report.user_sos:
        chip_html.append('<span class="ws-echo-chip crit">USER SOS</span>')
    if report.auto_sos:
        chip_html.append('<span class="ws-echo-chip crit">AUTO SOS</span>')
    if report.n_broadcasts >= 1:
        chip_html.append(
            f'<span class="ws-echo-chip">{report.n_broadcasts} broadcast(s)</span>'
        )

    depart_str = (
        report.depart_at.strftime("%a %d %b · %H:%M") if report.depart_at else "—"
    )
    arrived_str = (
        report.arrived_at.strftime("%H:%M") if report.arrived_at else "(in progress)"
    )

    st.markdown(
        f"""
        <div class="ws-echo-hero" style="--hue:{hue}; --glow:{glow};">
          <div class="ws-echo-ring" style="--hue:{hue}; --pct:{report.trip_score}; --glow:{glow};">
            <div class="ws-echo-ring-inner">
              <div class="ws-echo-ring-score">{report.trip_score:.0f}</div>
              <div class="ws-echo-ring-of100">/ 100</div>
              <div class="ws-echo-ring-band">{_esc(report.band)}</div>
            </div>
          </div>
          <div class="ws-echo-hero-body">
            <span class="ws-echo-pill" style="--hue:{hue}; --pill-bg:{pill_bg};">
              Echo · debrief
            </span>
            <div class="ws-echo-hero-title">{_echo_rec_to_html(report.headline)}</div>
            <div class="ws-echo-hero-detail">
              <b>{_esc(report.origin_label)}</b> → <b>{_esc(report.dest_label)}</b>
              · departed {_esc(depart_str)} · arrived {_esc(arrived_str)}
            </div>
            <div class="ws-echo-hero-detail">{_echo_rec_to_html(report.advisory_line)}</div>
            <div class="ws-echo-hero-meta">{"".join(chip_html)}</div>
          </div>
          <div class="ws-echo-mood" style="--mood-hue:{mood_hue}; --mood-bg:{mood_bg};">
            <div class="ws-echo-mood-glyph">{mood_glyph}</div>
            <div class="ws-echo-mood-label">{_esc(report.mood)}</div>
            <div class="ws-echo-mood-mini">mood</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---- 4-tile factor strip ----
    fcells: list[str] = []
    for f in report.factors:
        rim = _ECHO_BAND_HUE.get(_safety_band(int(f.value)), "#9FD3FF")
        fcells.append(
            f'<div class="ws-echo-factor" style="--rim:{rim};">'
            f'  <div class="ws-echo-factor-label">{_esc(f.label)}</div>'
            f'  <div class="ws-echo-factor-value">{f.value:.0f}</div>'
            f'  <div class="ws-echo-factor-small">weight {f.weight:.2f} · contrib {f.contribution:.1f}</div>'
            f'  <div class="ws-echo-factor-detail">{_esc(f.detail)}</div>'
            f'</div>'
        )
    st.markdown(
        f'<div class="ws-echo-factors">{"".join(fcells)}</div>',
        unsafe_allow_html=True,
    )

    # ---- corridor strip ----
    if report.corridor:
        st.markdown(
            '<div class="ws-echo-section-title">Realised corridor — risk by km</div>'
            '<div class="ws-echo-section-sub">'
            'Greener = safer. Diagonal hatch = inside a geofenced risk polygon. '
            'Sampled from the trip heartbeats; static-corridor fallback when no '
            'heartbeats were recorded.</div>',
            unsafe_allow_html=True,
        )
        cells: list[str] = []
        for s in report.corridor:
            chue = _echo_risk_hue(s.risk)
            bg = _hex_to_rgba(chue, 0.75)
            cls = "ws-echo-corridor-cell"
            if s.inside_geofence:
                cls += " fence"
            title = (
                f"{s.km:.2f} km · risk {s.risk:.2f}"
                + (" · inside geofence" if s.inside_geofence else "")
            )
            cells.append(
                f'<div class="{cls}" style="--bg:{bg};" title="{_esc(title)}"></div>'
            )
        st.markdown(
            f'<div class="ws-echo-corridor">{"".join(cells)}</div>'
            f'<div class="ws-echo-corridor-legend">'
            f'<span>0 km · {_esc(report.origin_label)}</span>'
            f'<span>{report.distance_km:.1f} km · {_esc(report.dest_label)}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ---- counterfactual ----
    if report.scenarios:
        st.markdown(
            '<div class="ws-echo-section-title">Counterfactual — what other flavors would have scored</div>'
            '<div class="ws-echo-section-sub">'
            'Each card re-plans your trip at the same depart-time. Δ rows quote '
            'the saving (or cost) vs the actual run. The strongest alternative is '
            'highlighted.</div>',
            unsafe_allow_html=True,
        )
        cards: list[str] = []
        for s in report.scenarios:
            shue = _ECHO_BAND_HUE.get(s.band, s.band_color)
            sglow = _hex_to_rgba(shue, 0.22)
            classes = ["ws-echo-cf"]
            is_winner = (
                report.best_alternative is not None
                and s.label == report.best_alternative
            )
            if is_winner:
                classes.append("win")
            actual_pill = (
                '<span class="ws-echo-cf-pill">your trip</span>' if s.is_actual else
                ('<span class="ws-echo-cf-pill">best alt</span>' if is_winner else "")
            )
            glyph = _ECHO_SCENARIO_GLYPH.get(s.label, "•")
            delta_html = ""
            if not s.is_actual:
                dts = s.delta_trip_score
                drk = s.delta_risk_km
                de = s.delta_eta_minutes
                dd = s.delta_distance_km
                dms = s.delta_min_safety
                cls_dts = "pos" if dts >= 0 else "neg"
                cls_drk = "pos" if drk >= 0 else "neg"
                de_str = f"{de:+.0f} min"
                dd_str = f"{dd:+.2f} km"
                delta_html = (
                    f'<div class="ws-echo-cf-delta">'
                    f'<span>Δ score <b class="{cls_dts}">{dts:+.1f}</b></span>'
                    f'<span>Δ risk-km <b class="{cls_drk}">{drk:+.2f}</b></span>'
                    f'<span>Δ time <b>{de_str}</b></span>'
                    f'<span>Δ dist <b>{dd_str}</b></span>'
                    f'<span>Δ min-safety <b>{dms:+d}</b></span>'
                    f'</div>'
                )
            cards.append(
                f'<div class="{ " ".join(classes) }" '
                f'style="--hue:{shue}; --glow:{sglow};">'
                f'  <div class="ws-echo-cf-head">'
                f'    <span class="ws-echo-cf-glyph">{glyph}</span>'
                f'    <span class="ws-echo-cf-label">{_esc(s.label)}</span>'
                f'    {actual_pill}'
                f'  </div>'
                f'  <div class="ws-echo-cf-score">{s.exposure_score:.0f}</div>'
                f'  <div class="ws-echo-cf-band">{_esc(s.band)}</div>'
                f'  <div class="ws-echo-cf-stat">'
                f'    <span>risk-km</span><b>{s.risk_km:.2f}</b>'
                f'  </div>'
                f'  <div class="ws-echo-cf-stat">'
                f'    <span>{s.distance_km:.1f} km · ETA {s.eta_minutes:.0f} min</span>'
                f'    <span>min {s.min_safety}</span>'
                f'  </div>'
                f'  {delta_html}'
                f'</div>'
            )
        st.markdown(
            f'<div class="ws-echo-cf-grid">{"".join(cards)}</div>',
            unsafe_allow_html=True,
        )

    # ---- calibration ----
    if report.calibration is not None:
        cal = report.calibration
        chue = _ECHO_CALIB_HUE.get(cal.band, cal.band_color)
        # pct: invert brier into a 0..100 dial (1 - brier).
        dial_pct = max(0.0, min(100.0, 100.0 * (1.0 - cal.brier)))
        st.markdown(
            '<div class="ws-echo-section-title">Alert calibration</div>'
            '<div class="ws-echo-section-sub">'
            'How well the live-trip risk-ahead predictions tracked what '
            'actually happened on the trace. Sharp = every alert resolved into '
            'an actual high-risk stretch within 90 s.</div>',
            unsafe_allow_html=True,
        )
        stat_chips: list[str] = []
        stat_chips.append(
            f'<span class="ws-echo-calib-stat">{cal.n_risk_ahead_alerts} alert(s)</span>'
        )
        stat_chips.append(
            f'<span class="ws-echo-calib-stat pos">TP {cal.n_true_positive}</span>'
        )
        stat_chips.append(
            f'<span class="ws-echo-calib-stat neg">FA {cal.n_false_alarm}</span>'
        )
        stat_chips.append(
            f'<span class="ws-echo-calib-stat miss">Miss {cal.n_miss}</span>'
        )
        stat_chips.append(
            f'<span class="ws-echo-calib-stat">{cal.n_heartbeats} heartbeats</span>'
        )
        st.markdown(
            f"""
            <div class="ws-echo-calib" style="--hue:{chue};">
              <div class="ws-echo-calib-dial" style="--hue:{chue}; --pct:{dial_pct};">
                <div class="ws-echo-calib-dial-inner">
                  <div class="ws-echo-calib-band">{_esc(cal.band)}</div>
                  <div class="ws-echo-calib-brier">brier {cal.brier:.2f}</div>
                </div>
              </div>
              <div class="ws-echo-calib-body">
                <div class="ws-echo-calib-stat-row">{"".join(stat_chips)}</div>
                <div class="ws-echo-calib-summary">{_echo_rec_to_html(cal.summary)}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ---- timeline ----
    if report.timeline:
        st.markdown(
            '<div class="ws-echo-section-title">Event timeline</div>'
            '<div class="ws-echo-section-sub">'
            'Every alert + milestone the Live Trip Companion emitted, ordered by '
            'time. Left rail colour mirrors severity.</div>',
            unsafe_allow_html=True,
        )
        rows: list[str] = []
        for ev in report.timeline[:60]:
            km_html = (
                f'<div class="ws-echo-tl-km">{ev.rel_km:.1f} km</div>'
                if ev.rel_km is not None else ''
            )
            rows.append(
                f'<div class="ws-echo-tl-row" style="--accent:{ev.accent};">'
                f'  <div class="ws-echo-tl-ts">{ev.ts.strftime("%H:%M:%S")}</div>'
                f'  <div class="ws-echo-tl-icon">{ev.icon}</div>'
                f'  <div class="ws-echo-tl-msg">'
                f'    <span class="kind">{_esc(ev.sub_kind)}</span>'
                f'    {_echo_rec_to_html(ev.message)}'
                f'  </div>'
                f'  {km_html}'
                f'</div>'
            )
        st.markdown(
            f'<div class="ws-echo-timeline">{"".join(rows)}</div>',
            unsafe_allow_html=True,
        )
        if len(report.timeline) > 60:
            st.caption(f"… plus {len(report.timeline) - 60} more events in the JSON export.")

    # ---- lessons ----
    if report.lessons:
        st.markdown(
            '<div class="ws-echo-section-title">Lessons &amp; plan-of-next-trip</div>'
            '<div class="ws-echo-section-sub">'
            'Deterministic bullets keyed to this debrief\'s own numbers. Each '
            'one names the WaySafe tab to open next.</div>',
            unsafe_allow_html=True,
        )
        items: list[str] = []
        for l in report.lessons:
            cls = "ws-echo-lesson"
            head = l[:2]
            if head in ("🆘", "🔴", "⏸️"):
                cls += " crit"
            elif head in ("🛡", "✅", "📈", "🟢"):
                cls += " good"
            elif head in ("🚷", "⚠️", "🔧", "📉"):
                cls += " prio"
            items.append(
                f'<div class="{cls}">{_echo_rec_to_html(l)}</div>'
            )
        st.markdown(
            f'<div class="ws-echo-lessons">{"".join(items)}</div>',
            unsafe_allow_html=True,
        )


def render_echo_empty(
    hint: str = (
        "Echo composes a post-trip debrief from a completed Live Trip. "
        "Run a journey in the **Live Trip** tab — or load the seeded "
        "demo trip below — and come back here for the verdict."
    ),
) -> None:
    st.markdown(_ECHO_CSS, unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="ws-echo-empty">
          <div class="ws-echo-empty-title">Echo idle</div>
          <div>{_esc(hint)}</div>
          <small style="color:#8892A6;">
          Echo composes a verdict only — it adds zero new physics. Every number
          in the brief traces back to <code>safety.point_risk</code>, the
          <code>routing</code> A*, or the live-trip heartbeats. Pure-Python,
          zero new deps.
          </small>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ==========================================================================
# Prism — Persona-Aware Risk Lens (Day 71)
# ==========================================================================
_PRISM_CSS = """
<style>
:root {
  --prism-safe:    #7ED9A5;
  --prism-caut:    #F6C560;
  --prism-high:    #F58F5B;
  --prism-dgr:     #EF6D7A;
  --prism-line:    rgba(255,255,255,0.08);
  --prism-glass:   rgba(255,255,255,0.03);
}
.ws-prism-hero {
  position: relative;
  display: grid;
  grid-template-columns: 168px 1fr auto;
  gap: 22px;
  align-items: center;
  padding: 22px 24px;
  margin: 8px 0 18px 0;
  border-radius: 20px;
  background:
    radial-gradient(ellipse 60% 70% at 18% 10%, var(--glow), transparent 70%),
    linear-gradient(135deg, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0.01) 100%);
  border: 1px solid var(--hue, #3DA9FC);
  box-shadow: 0 10px 36px var(--glow, rgba(61,169,252,0.20));
}
.ws-prism-ring {
  position: relative;
  width: 168px; height: 168px; border-radius: 50%;
  background:
    conic-gradient(var(--hue) calc(var(--pct,0) * 1%), rgba(255,255,255,0.06) 0);
  display: grid; place-items: center;
  box-shadow: 0 0 30px var(--glow, rgba(61,169,252,0.22));
}
.ws-prism-ring::after {
  content: "";
  position: absolute; inset: 12px;
  border-radius: 50%;
  background: #0E1117;
}
.ws-prism-ring-inner {
  position: relative; z-index: 1;
  display: grid; place-items: center;
  text-align: center;
}
.ws-prism-persona-glyph {
  font-size: 40px; line-height: 1;
}
.ws-prism-persona-name {
  font-size: 12px; color: #E6E9F2; margin-top: 6px; font-weight: 700;
  letter-spacing: 0.02em;
}
.ws-prism-persona-band {
  font-size: 11px; color: var(--hue); margin-top: 4px; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.10em;
}
.ws-prism-hero-body { display: flex; flex-direction: column; gap: 6px; }
.ws-prism-pill {
  align-self: flex-start;
  display: inline-flex; gap: 8px; align-items: center;
  padding: 4px 12px; border-radius: 999px;
  background: var(--pill-bg, rgba(61,169,252,0.14));
  border: 1px solid var(--hue, #3DA9FC);
  color: var(--hue, #3DA9FC);
  font-size: 11px; font-weight: 800;
  text-transform: uppercase; letter-spacing: 0.08em;
}
.ws-prism-hero-title {
  font-size: 22px; font-weight: 800; color: #E6E9F2;
  letter-spacing: -0.02em; margin-top: 2px;
}
.ws-prism-hero-blurb {
  font-size: 13px; color: #B0B7CC; margin: 4px 0 6px 0; line-height: 1.4;
}
.ws-prism-hero-chips {
  display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px;
}
.ws-prism-chip {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 3px 10px; border-radius: 999px;
  background: rgba(255,255,255,0.05);
  border: 1px solid rgba(255,255,255,0.10);
  color: #C9CFDD; font-size: 11px; font-weight: 600;
}
.ws-prism-chip b { color: #E6E9F2; }
.ws-prism-mood {
  display: grid; place-items: center;
  padding: 12px 18px; border-radius: 14px;
  background: var(--glow, rgba(61,169,252,0.12));
  border: 1px solid var(--hue, #3DA9FC);
  min-width: 140px;
}
.ws-prism-mood-glyph { font-size: 28px; }
.ws-prism-mood-name  { font-size: 12px; color: var(--hue); font-weight: 800;
                       text-transform: uppercase; letter-spacing: 0.08em; margin-top: 4px; }
.ws-prism-mood-note  { font-size: 11px; color: #C9CFDD; margin-top: 2px; }

/* Persona chip strip — click one to switch persona. */
.ws-prism-personas {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px; margin: 8px 0 16px 0;
}
.ws-prism-persona-card {
  padding: 12px 14px; border-radius: 14px;
  background: var(--prism-glass);
  border: 1px solid var(--prism-line);
  display: flex; flex-direction: column; gap: 4px;
  transition: transform .12s ease, border-color .12s ease;
}
.ws-prism-persona-card.active {
  border-color: var(--hue, #3DA9FC);
  background:
    radial-gradient(ellipse 60% 80% at 30% 20%, var(--glow), transparent 70%),
    var(--prism-glass);
  box-shadow: 0 6px 22px var(--glow, rgba(61,169,252,0.18));
}
.ws-prism-persona-glyph-sm { font-size: 22px; line-height: 1; }
.ws-prism-persona-label-sm { font-size: 12px; color: #E6E9F2; font-weight: 700; }
.ws-prism-persona-alpha    { font-size: 10px; color: #8892A6; font-weight: 600; }
.ws-prism-persona-blurb-sm { font-size: 11px; color: #C9CFDD; line-height: 1.35; }

/* Watched points grid — one card per point with base vs persona rings. */
.ws-prism-points {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 14px; margin-top: 10px;
}
.ws-prism-point {
  padding: 14px 16px; border-radius: 16px;
  background: var(--prism-glass);
  border: 1px solid var(--prism-line);
  display: flex; flex-direction: column; gap: 10px;
  border-left: 4px solid var(--hue, #3DA9FC);
}
.ws-prism-point-header {
  display: flex; justify-content: space-between; align-items: baseline; gap: 8px;
}
.ws-prism-point-label {
  font-size: 14px; font-weight: 700; color: #E6E9F2;
}
.ws-prism-point-delta {
  font-size: 12px; font-weight: 800;
  padding: 2px 10px; border-radius: 999px;
  background: var(--pill-bg, rgba(255,255,255,0.06));
  color: var(--hue, #C9CFDD);
  border: 1px solid var(--hue, rgba(255,255,255,0.10));
}
.ws-prism-dual-rings {
  display: grid; grid-template-columns: 1fr 1fr; gap: 12px;
  align-items: center;
}
.ws-prism-ring-sm {
  position: relative;
  width: 90px; height: 90px; border-radius: 50%;
  background:
    conic-gradient(var(--hue) calc(var(--pct,0) * 1%), rgba(255,255,255,0.06) 0);
  display: grid; place-items: center;
  margin: 0 auto;
}
.ws-prism-ring-sm::after {
  content: "";
  position: absolute; inset: 8px;
  border-radius: 50%;
  background: #0E1117;
}
.ws-prism-ring-sm-inner {
  position: relative; z-index: 1;
  text-align: center;
}
.ws-prism-ring-sm-score {
  font-size: 22px; font-weight: 800; color: #E6E9F2; line-height: 1;
}
.ws-prism-ring-sm-tag { font-size: 10px; color: #8892A6; margin-top: 2px;
                        text-transform: uppercase; letter-spacing: 0.08em; }
.ws-prism-ring-sm-cap { font-size: 10px; color: #C9CFDD; margin-top: 4px; font-weight: 600; }

.ws-prism-headline { font-size: 12px; color: #B0B7CC; line-height: 1.4; }

/* Factor delta bars — one row per factor, base + persona bar side by side. */
.ws-prism-factors { display: flex; flex-direction: column; gap: 6px; margin-top: 8px; }
.ws-prism-factor-row {
  display: grid; grid-template-columns: 1fr auto; gap: 6px;
  padding: 6px 8px; border-radius: 10px;
  background: rgba(255,255,255,0.03);
  border-left: 3px solid var(--hue, rgba(255,255,255,0.10));
}
.ws-prism-factor-label { font-size: 11px; color: #E6E9F2; font-weight: 600; }
.ws-prism-factor-reason { font-size: 10px; color: #8892A6; margin-top: 2px; }
.ws-prism-factor-values {
  display: flex; gap: 8px; align-items: baseline;
  font-size: 11px; font-weight: 700; color: #C9CFDD;
}
.ws-prism-factor-arrow { color: var(--hue, #C9CFDD); }
.ws-prism-factor-delta {
  font-weight: 800; color: var(--hue, #C9CFDD);
}
.ws-prism-factor-bar {
  height: 4px; border-radius: 4px; background: rgba(255,255,255,0.06);
  overflow: hidden; margin-top: 6px; position: relative;
}
.ws-prism-factor-bar > span {
  display: block; height: 100%;
  background: var(--hue, #3DA9FC);
}
.ws-prism-extras {
  margin-top: 8px; padding: 8px 10px; border-radius: 10px;
  background: rgba(239,109,122,0.08); border: 1px solid rgba(239,109,122,0.35);
}
.ws-prism-extras-title {
  font-size: 10px; color: #EF6D7A; font-weight: 800;
  text-transform: uppercase; letter-spacing: 0.10em; margin-bottom: 4px;
}
.ws-prism-extras-item { font-size: 11px; color: #FDDDD9; margin: 2px 0; }
.ws-prism-extras-item small { color: #C9CFDD; }

/* Lessons + checklist */
.ws-prism-lessons { display: flex; flex-direction: column; gap: 6px; margin-top: 12px; }
.ws-prism-lesson {
  padding: 10px 12px; border-radius: 10px;
  background: var(--prism-glass);
  border-left: 3px solid var(--hue, #7ED9A5);
  font-size: 12px; color: #E6E9F2; line-height: 1.45;
}
.ws-prism-checklist {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 8px; margin-top: 8px;
}
.ws-prism-check {
  padding: 10px 12px; border-radius: 10px;
  background: var(--prism-glass);
  border: 1px solid var(--prism-line);
  font-size: 12px; color: #E6E9F2; line-height: 1.4;
  display: flex; gap: 8px; align-items: flex-start;
}
.ws-prism-check-box {
  flex-shrink: 0; width: 14px; height: 14px; border-radius: 4px;
  border: 1.5px solid #667080; margin-top: 2px;
}
.ws-prism-section-title {
  font-size: 13px; font-weight: 800; color: #E6E9F2;
  margin: 14px 0 6px 0; text-transform: uppercase; letter-spacing: 0.08em;
}

/* Cross-persona matrix */
.ws-prism-matrix {
  margin-top: 14px; overflow-x: auto;
  padding: 12px; border-radius: 14px;
  background: var(--prism-glass); border: 1px solid var(--prism-line);
}
.ws-prism-matrix-table {
  width: 100%; border-collapse: collapse; font-size: 12px;
}
.ws-prism-matrix-table th, .ws-prism-matrix-table td {
  padding: 8px 10px; text-align: center;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}
.ws-prism-matrix-table th {
  color: #C9CFDD; font-weight: 700; text-transform: uppercase;
  font-size: 10px; letter-spacing: 0.08em;
}
.ws-prism-matrix-table td:first-child, .ws-prism-matrix-table th:first-child {
  text-align: left;
}
.ws-prism-matrix-row-label { color: #E6E9F2; font-weight: 700; }
.ws-prism-matrix-base { color: #C9CFDD; font-weight: 600; }
.ws-prism-matrix-cell {
  display: inline-block; padding: 3px 8px; border-radius: 8px;
  font-weight: 800; min-width: 44px;
}
.ws-prism-matrix-agg {
  background: rgba(255,255,255,0.03); font-weight: 800;
}
.ws-prism-matrix-aggcell {
  color: #E6E9F2; font-weight: 800;
}

.ws-prism-empty {
  padding: 24px; border-radius: 16px;
  background: var(--prism-glass); border: 1px dashed var(--prism-line);
  text-align: center;
}
.ws-prism-empty-title {
  font-size: 14px; font-weight: 800; color: #E6E9F2; margin-bottom: 6px;
}
</style>
"""


def _prism_hue(band: str) -> Tuple[str, str, str]:
    """(main hue, glow, pill background) for a band."""
    hue_map = {
        "Safe":      ("#7ED9A5", "rgba(126,217,165,0.22)", "rgba(126,217,165,0.14)"),
        "Caution":   ("#F6C560", "rgba(246,197,96,0.22)",  "rgba(246,197,96,0.14)"),
        "High Risk": ("#F58F5B", "rgba(245,143,91,0.24)",  "rgba(245,143,91,0.14)"),
        "Danger":    ("#EF6D7A", "rgba(239,109,122,0.26)", "rgba(239,109,122,0.14)"),
    }
    return hue_map.get(band, hue_map["Caution"])


def _prism_advisory_glyph(level: str) -> str:
    return {"All clear": "🟢", "Caution": "🟡",
            "Elevated": "🟠", "Critical": "🔴"}.get(level, "🟡")


def _prism_delta_hue(delta: int) -> Tuple[str, str, str]:
    """Hue for the delta pill — coral when the persona feels worse, lime when better."""
    if delta <= -8:
        return ("#EF6D7A", "rgba(239,109,122,0.20)", "rgba(239,109,122,0.14)")
    if delta <= -3:
        return ("#F58F5B", "rgba(245,143,91,0.20)", "rgba(245,143,91,0.14)")
    if delta >= 5:
        return ("#7ED9A5", "rgba(126,217,165,0.20)", "rgba(126,217,165,0.14)")
    return ("#C9CFDD", "rgba(255,255,255,0.08)", "rgba(255,255,255,0.06)")


def render_prism(report, matrix: dict | None = None) -> None:
    """Render a `PrismReport` — hero, persona chip strip, watched-point cards,
    lessons, checklist, and (optionally) a cross-persona matrix."""
    if report is None:
        render_prism_empty()
        return

    st.markdown(_PRISM_CSS, unsafe_allow_html=True)

    # ---- Hero ------------------------------------------------------------
    persona_hue = "#B4A0FF"
    persona_glow = "rgba(180,160,255,0.22)"
    persona_pill_bg = "rgba(180,160,255,0.14)"
    # Colour the hero by the aggregate persona advisory (worst point's rung).
    adv_hue, adv_glow, adv_pill = _prism_hue(
        {"All clear": "Safe", "Caution": "Caution",
         "Elevated": "High Risk", "Critical": "Danger"}.get(report.advisory, "Caution")
    )

    avg_pct = max(0, min(100, report.avg_persona_score))
    st.markdown(
        f"""
        <div class="ws-prism-hero" style="--hue:{adv_hue};--glow:{adv_glow};">
          <div class="ws-prism-ring" style="--hue:{adv_hue};--pct:{avg_pct};--glow:{adv_glow};">
            <div class="ws-prism-ring-inner">
              <div class="ws-prism-persona-glyph">{_esc(report.persona_icon)}</div>
              <div class="ws-prism-persona-name">{_esc(report.persona_label)}</div>
              <div class="ws-prism-persona-band">{report.avg_persona_score}/100</div>
            </div>
          </div>
          <div class="ws-prism-hero-body">
            <div class="ws-prism-pill" style="--pill-bg:{adv_pill};--hue:{adv_hue};">
              PRISM · {_esc(report.advisory).upper()}
            </div>
            <div class="ws-prism-hero-title">{_esc(report.headline)}</div>
            <div class="ws-prism-hero-blurb">{_esc(report.persona_blurb)}</div>
            <div class="ws-prism-hero-chips">
              <span class="ws-prism-chip">watch-list avg <b>base {report.avg_base_score}</b> → <b>persona {report.avg_persona_score}</b></span>
              <span class="ws-prism-chip">route α <b>{report.route_alpha:.1f}</b></span>
              <span class="ws-prism-chip">broadcast every <b>{report.broadcast_minutes} min</b></span>
              <span class="ws-prism-chip">Safe ≥{report.band_thresholds[0]} · Caution ≥{report.band_thresholds[1]} · High Risk ≥{report.band_thresholds[2]}</span>
              {"<span class='ws-prism-chip'>advisory <b>+" + str(report.advisory_bump_level) + " rung</b> for this persona</span>" if report.advisory_bump_level > 0 else ""}
            </div>
          </div>
          <div class="ws-prism-mood" style="--hue:{adv_hue};--glow:{adv_glow};">
            <div class="ws-prism-mood-glyph">{_prism_advisory_glyph(report.advisory)}</div>
            <div class="ws-prism-mood-name">{_esc(report.advisory)}</div>
            <div class="ws-prism-mood-note">worst-of {len(report.points)} points</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---- Watched-point cards --------------------------------------------
    st.markdown('<div class="ws-prism-section-title">Watched points — base vs persona</div>',
                unsafe_allow_html=True)

    if not report.points:
        st.info("No watched points to score under this persona.")
    else:
        cards_html: List[str] = ['<div class="ws-prism-points">']
        for p in report.points:
            base_hue, base_glow, _ = _prism_hue(p.base_band)
            pers_hue, pers_glow, pers_pill = _prism_hue(p.persona_band)
            d_hue, d_glow, d_pill = _prism_delta_hue(p.delta)
            base_pct = max(0, min(100, p.base_score))
            pers_pct = max(0, min(100, p.persona_score))
            arrow_txt = "→" if p.delta == 0 else ("↑" if p.delta > 0 else "↓")

            # Factor delta rows
            factor_rows: List[str] = []
            for f in p.factors:
                # Colour keyed to which way the delta moved.
                if f.delta < -1:
                    fhue = "#EF6D7A"
                elif f.delta > 1:
                    fhue = "#7ED9A5"
                else:
                    fhue = "#C9CFDD"
                delta_disp = f"{f.delta:+.1f}"
                factor_rows.append(f"""
                <div class="ws-prism-factor-row" style="--hue:{fhue};">
                  <div>
                    <div class="ws-prism-factor-label">{_esc(f.label)}</div>
                    <div class="ws-prism-factor-reason">{_esc(f.reason or '')}</div>
                  </div>
                  <div class="ws-prism-factor-values">
                    <span>{f.base_impact:+.1f}</span>
                    <span class="ws-prism-factor-arrow">→</span>
                    <span>{f.persona_impact:+.1f}</span>
                    <span class="ws-prism-factor-delta">({delta_disp})</span>
                  </div>
                </div>
                """)
            factors_block = ('<div class="ws-prism-factors">' + "".join(factor_rows) + "</div>"
                             if factor_rows else "")

            # Extras block
            extras_block = ""
            if p.extras:
                items = "".join(
                    f'<div class="ws-prism-extras-item">• {_esc(e.label)} '
                    f'<small>({e.persona_impact:+.1f} · {_esc(e.reason or "")})</small></div>'
                    for e in p.extras
                )
                extras_block = f"""
                <div class="ws-prism-extras">
                  <div class="ws-prism-extras-title">Persona-only extras</div>
                  {items}
                </div>
                """

            cards_html.append(f"""
            <div class="ws-prism-point" style="--hue:{pers_hue};--glow:{pers_glow};">
              <div class="ws-prism-point-header">
                <div class="ws-prism-point-label">{_esc(p.label)}</div>
                <div class="ws-prism-point-delta" style="--hue:{d_hue};--pill-bg:{d_pill};">
                  {p.delta:+d} pts {arrow_txt}
                </div>
              </div>
              <div class="ws-prism-dual-rings">
                <div>
                  <div class="ws-prism-ring-sm" style="--hue:{base_hue};--pct:{base_pct};">
                    <div class="ws-prism-ring-sm-inner">
                      <div class="ws-prism-ring-sm-score">{p.base_score}</div>
                      <div class="ws-prism-ring-sm-tag">Base</div>
                    </div>
                  </div>
                  <div class="ws-prism-ring-sm-cap" style="text-align:center;">{_esc(p.base_band)}</div>
                </div>
                <div>
                  <div class="ws-prism-ring-sm" style="--hue:{pers_hue};--pct:{pers_pct};">
                    <div class="ws-prism-ring-sm-inner">
                      <div class="ws-prism-ring-sm-score">{p.persona_score}</div>
                      <div class="ws-prism-ring-sm-tag">Persona</div>
                    </div>
                  </div>
                  <div class="ws-prism-ring-sm-cap" style="color:{pers_hue};text-align:center;">
                    {_esc(p.persona_band)} · {_esc(p.advisory_level)}
                  </div>
                </div>
              </div>
              <div class="ws-prism-headline">{_esc(p.headline)}</div>
              {factors_block}
              {extras_block}
            </div>
            """)
        cards_html.append("</div>")
        st.markdown("".join(cards_html), unsafe_allow_html=True)

    # ---- Lessons ---------------------------------------------------------
    st.markdown('<div class="ws-prism-section-title">Lessons for this persona</div>',
                unsafe_allow_html=True)
    lesson_html: List[str] = ['<div class="ws-prism-lessons">']
    for l in report.lessons:
        # Colour the left rail from the leading glyph.
        if l.startswith(("🔴", "🆘")):
            hue = "#EF6D7A"
        elif l.startswith(("🟠", "📉", "⚠️", "🚑", "⏱")):
            hue = "#F58F5B"
        elif l.startswith(("🟢", "🛡", "✅")):
            hue = "#7ED9A5"
        else:
            hue = "#7EB6EF"
        lesson_html.append(
            f'<div class="ws-prism-lesson" style="--hue:{hue};">{_esc(l)}</div>'
        )
    lesson_html.append("</div>")
    st.markdown("".join(lesson_html), unsafe_allow_html=True)

    # ---- Checklist -------------------------------------------------------
    if report.checklist:
        st.markdown('<div class="ws-prism-section-title">Pre-departure checklist</div>',
                    unsafe_allow_html=True)
        chk_html: List[str] = ['<div class="ws-prism-checklist">']
        for item in report.checklist:
            chk_html.append(f"""
            <div class="ws-prism-check">
              <div class="ws-prism-check-box"></div>
              <div>{_esc(item)}</div>
            </div>
            """)
        chk_html.append("</div>")
        st.markdown("".join(chk_html), unsafe_allow_html=True)

    # ---- Cross-persona matrix -------------------------------------------
    if matrix and matrix.get("rows"):
        st.markdown('<div class="ws-prism-section-title">Cross-persona matrix — same corridor, different traveller</div>',
                    unsafe_allow_html=True)
        cols = matrix["columns"]
        header = "".join(
            f"<th>{_esc(c['icon'])}<br><span style='font-size:10px;'>{_esc(c['label'])}</span></th>"
            for c in cols
        )
        rows_html: List[str] = []
        for r in matrix["rows"]:
            base = r["base_score"]
            cells_html = []
            for c in r["cells"]:
                chue, _, cpill = _prism_hue(c["persona_band"])
                cells_html.append(
                    f'<td><span class="ws-prism-matrix-cell" '
                    f'style="background:{cpill};color:{chue};">'
                    f'{c["persona_score"]}</span></td>'
                )
            rows_html.append(
                f'<tr><td class="ws-prism-matrix-row-label">{_esc(r["label"])}</td>'
                f'<td class="ws-prism-matrix-base">{base}</td>'
                + "".join(cells_html) + "</tr>"
            )
        # Aggregate row
        agg_map = {c["persona_id"]: c["avg_persona_score"] for c in matrix["column_aggregates"]}
        agg_cells = []
        for c in cols:
            v = agg_map.get(c["id"], 0)
            band = "Safe" if v >= 80 else "Caution" if v >= 60 else "High Risk" if v >= 35 else "Danger"
            chue, _, cpill = _prism_hue(band)
            agg_cells.append(
                f'<td><span class="ws-prism-matrix-cell" '
                f'style="background:{cpill};color:{chue};">{v}</span></td>'
            )
        rows_html.append(
            '<tr class="ws-prism-matrix-agg"><td class="ws-prism-matrix-row-label">Watch-list avg</td>'
            '<td class="ws-prism-matrix-aggcell">—</td>' + "".join(agg_cells) + "</tr>"
        )
        table_html = f"""
        <div class="ws-prism-matrix">
          <table class="ws-prism-matrix-table">
            <thead>
              <tr><th>Point</th><th>Base</th>{header}</tr>
            </thead>
            <tbody>
              {"".join(rows_html)}
            </tbody>
          </table>
        </div>
        """
        st.markdown(table_html, unsafe_allow_html=True)

        best = matrix.get("best_persona_id")
        worst = matrix.get("worst_persona_id")
        if best and worst:
            b = next((c for c in matrix["column_aggregates"] if c["persona_id"] == best), None)
            w = next((c for c in matrix["column_aggregates"] if c["persona_id"] == worst), None)
            if b and w:
                st.caption(
                    f"Best under this watch-list: **{b['persona_icon']} {b['persona_label']}** "
                    f"({b['avg_persona_score']}) · "
                    f"toughest for **{w['persona_icon']} {w['persona_label']}** "
                    f"({w['avg_persona_score']})."
                )


def render_prism_empty(
    hint: str = (
        "Prism re-prices every watched point through one of six traveller personas — "
        "solo woman, family with kids, senior, business, adventure, or backpacker group. "
        "Pick a persona above to see how the same corridor reads for someone else."
    ),
) -> None:
    st.markdown(_PRISM_CSS, unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="ws-prism-empty">
          <div class="ws-prism-empty-title">Prism idle</div>
          <div>{_esc(hint)}</div>
          <small style="color:#8892A6;">
          Prism is a lens, not new physics. Every number traces back to
          <code>safety.compute_safety</code> — Prism just re-weights the same
          factor ledger under the chosen persona. Pure-Python, zero new deps.
          </small>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ------------------------------------------------------------------ Odyssey
# Day 76: Multi-Day Trip Composer.
#
# Renders a `odyssey.TripReport`: hero score ring, per-day accordion strip,
# corridor heat rows, weakest-link callout with ranked swaps, drift +
# persistence chips, and an ordered advisory block.


_ODYSSEY_CSS = """
<style>
:root {
  --od-serene:  #53E3A6;
  --od-solid:   #7BC5F1;
  --od-bumpy:   #F9C440;
  --od-frag:    #FF9F43;
  --od-crit:    #FF3D60;
  --od-line:    rgba(255,255,255,0.08);
  --od-glass:   rgba(255,255,255,0.03);
  --od-glass-2: rgba(255,255,255,0.055);
  --od-ink:     #E6E9F2;
  --od-mute:    #8892A6;
  --od-dim:     #6B7280;
}

.ws-od-hero {
  position: relative;
  display: grid;
  grid-template-columns: 172px 1fr auto;
  gap: 22px;
  align-items: center;
  padding: 22px 24px;
  margin: 6px 0 18px 0;
  border-radius: 22px;
  background:
    radial-gradient(ellipse 60% 70% at 18% 12%, var(--glow), transparent 70%),
    linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.008) 100%);
  border: 1px solid var(--hue, #7BC5F1);
  box-shadow: 0 12px 40px var(--glow, rgba(123,197,241,0.20));
}
.ws-od-ring {
  position: relative;
  width: 172px; height: 172px; border-radius: 50%;
  background: conic-gradient(var(--hue) calc(var(--pct,0) * 1%),
                             rgba(255,255,255,0.05) 0);
  display: grid; place-items: center;
  box-shadow: 0 0 32px var(--glow, rgba(123,197,241,0.22));
}
.ws-od-ring::after {
  content: "";
  position: absolute; inset: 12px;
  border-radius: 50%;
  background: #0E1117;
}
.ws-od-ring-inner {
  position: relative; z-index: 1;
  display: grid; place-items: center; text-align: center;
}
.ws-od-score {
  font-size: 42px; line-height: 1; font-weight: 900;
  color: var(--od-ink); letter-spacing: -0.02em;
}
.ws-od-score small { font-size: 14px; color: var(--od-mute); font-weight: 700; }
.ws-od-verdict {
  font-size: 11px; color: var(--hue); margin-top: 6px; font-weight: 800;
  text-transform: uppercase; letter-spacing: 0.14em;
}
.ws-od-hero-body { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.ws-od-pill {
  align-self: flex-start;
  display: inline-flex; gap: 8px; align-items: center;
  padding: 4px 12px; border-radius: 999px;
  background: var(--pill-bg, rgba(123,197,241,0.14));
  border: 1px solid var(--hue, #7BC5F1);
  color: var(--hue, #7BC5F1);
  font-size: 11px; font-weight: 800;
  text-transform: uppercase; letter-spacing: 0.10em;
}
.ws-od-hero-title {
  font-size: 22px; font-weight: 800; color: var(--od-ink);
  letter-spacing: -0.02em; margin-top: 2px;
}
.ws-od-hero-blurb {
  font-size: 13px; color: var(--od-mute); line-height: 1.45; margin: 4px 0 6px 0;
}
.ws-od-hero-chips {
  display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px;
}
.ws-od-chip {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 10px; border-radius: 999px;
  background: var(--od-glass-2);
  border: 1px solid var(--od-line);
  color: var(--od-ink); font-size: 11px; font-weight: 600;
}
.ws-od-chip b { color: var(--od-ink); font-weight: 800; }
.ws-od-chip.pos { color: var(--od-serene); border-color: rgba(83,227,166,0.28); }
.ws-od-chip.neg { color: var(--od-crit);   border-color: rgba(255,61,96,0.30); }
.ws-od-mood {
  display: grid; place-items: center; text-align: center;
  padding: 12px 16px;
  border-radius: 16px;
  background: linear-gradient(135deg, var(--glow) 0%, transparent 100%);
  border: 1px solid var(--hue, #7BC5F1);
  min-width: 130px;
}
.ws-od-mood-glyph { font-size: 34px; line-height: 1; }
.ws-od-mood-name  { font-size: 12px; font-weight: 800; color: var(--hue);
                    letter-spacing: 0.08em; text-transform: uppercase; margin-top: 4px; }
.ws-od-mood-note  { font-size: 10.5px; color: var(--od-mute); margin-top: 2px; }

/* --- Aggregate tiles ------------------------------------------------ */
.ws-od-tiles {
  display: grid;
  grid-template-columns: repeat(4, minmax(0,1fr));
  gap: 10px; margin: 6px 0 18px 0;
}
.ws-od-tile {
  padding: 12px 14px; border-radius: 14px;
  background: var(--od-glass); border: 1px solid var(--od-line);
}
.ws-od-tile-label { font-size: 10.5px; color: var(--od-mute);
                    text-transform: uppercase; letter-spacing: 0.10em; font-weight: 700; }
.ws-od-tile-value { font-size: 22px; color: var(--od-ink); font-weight: 800;
                    letter-spacing: -0.02em; margin-top: 4px; }
.ws-od-tile-hint  { font-size: 11px; color: var(--od-mute); margin-top: 2px; }

/* --- Day strip ------------------------------------------------------ */
.ws-od-section-title {
  font-size: 13px; color: var(--od-ink); font-weight: 800;
  margin: 14px 0 8px 2px;
  letter-spacing: 0.02em;
}
.ws-od-day-strip { display: flex; gap: 10px; overflow-x: auto; padding: 4px 0 12px 0; }
.ws-od-day-card {
  min-width: 220px; max-width: 260px;
  padding: 14px 14px 12px 14px;
  border-radius: 14px;
  background: linear-gradient(135deg, var(--glow) 0%, rgba(255,255,255,0.008) 100%);
  border: 1px solid var(--hue); flex: 0 0 auto;
}
.ws-od-day-head {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 6px;
}
.ws-od-day-num {
  padding: 2px 8px; border-radius: 999px;
  background: rgba(255,255,255,0.06);
  border: 1px solid var(--od-line);
  color: var(--od-ink); font-size: 10.5px; font-weight: 800;
  letter-spacing: 0.08em;
}
.ws-od-day-band {
  padding: 2px 10px; border-radius: 999px;
  background: var(--pill-bg);
  border: 1px solid var(--hue);
  color: var(--hue); font-size: 10px; font-weight: 800;
  letter-spacing: 0.10em; text-transform: uppercase;
}
.ws-od-day-title { font-size: 14px; font-weight: 800; color: var(--od-ink);
                   line-height: 1.25; margin: 2px 0 4px 0; }
.ws-od-day-date  { font-size: 11px; color: var(--od-mute); margin-bottom: 6px; }
.ws-od-day-score {
  display: flex; align-items: baseline; gap: 6px;
  color: var(--hue); font-weight: 900; font-size: 30px; letter-spacing: -0.02em;
  margin-bottom: 4px;
}
.ws-od-day-score small { color: var(--od-mute); font-size: 12px; font-weight: 700; }
.ws-od-day-reason { font-size: 11px; color: var(--od-mute); line-height: 1.35; }
.ws-od-day-sub {
  display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px;
}
.ws-od-daychip {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 2px 8px; border-radius: 999px;
  background: rgba(255,255,255,0.05);
  border: 1px solid var(--od-line);
  color: var(--od-ink); font-size: 10.5px; font-weight: 600;
}
.ws-od-daychip b { color: var(--od-ink); font-weight: 800; }

/* --- Day details (drill-in) ---------------------------------------- */
.ws-od-detail {
  padding: 14px 16px; border-radius: 14px;
  background: var(--od-glass); border: 1px solid var(--od-line);
  margin-bottom: 8px;
}
.ws-od-detail h4 {
  font-size: 13px; color: var(--od-ink); font-weight: 800;
  margin: 0 0 8px 0; letter-spacing: 0.02em;
}
.ws-od-leg-row {
  display: grid; grid-template-columns: 1fr auto auto auto auto; gap: 10px;
  padding: 8px 10px; border-radius: 10px;
  background: rgba(255,255,255,0.02);
  border: 1px solid var(--od-line); margin-bottom: 4px;
  align-items: center; font-size: 12.5px; color: var(--od-ink);
}
.ws-od-leg-arrow { color: var(--od-mute); font-weight: 800; margin: 0 4px; }
.ws-od-leg-num { color: var(--hue); font-weight: 800; font-variant-numeric: tabular-nums; }
.ws-od-leg-mini {
  color: var(--od-mute); font-size: 10.5px; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.08em;
}
.ws-od-leg-strip {
  height: 8px; border-radius: 4px; overflow: hidden;
  background: rgba(255,255,255,0.05);
  display: flex; margin: 6px 0 2px 0;
}
.ws-od-leg-strip span { display: block; height: 100%; flex: 1 1 0; min-width: 0; }
.ws-od-stop-row {
  display: grid; grid-template-columns: 1fr auto auto; gap: 12px;
  padding: 8px 10px; border-radius: 10px;
  background: rgba(255,255,255,0.02);
  border: 1px solid var(--od-line);
  align-items: center; margin-bottom: 4px; font-size: 12.5px; color: var(--od-ink);
}
.ws-od-stop-badge {
  padding: 2px 8px; border-radius: 999px;
  background: var(--pill-bg); border: 1px solid var(--hue);
  color: var(--hue); font-size: 10.5px; font-weight: 800;
  text-transform: uppercase; letter-spacing: 0.08em;
}

/* --- Weakest-link callout ------------------------------------------ */
.ws-od-weak {
  padding: 16px 18px; border-radius: 16px;
  background: linear-gradient(135deg, var(--glow) 0%, rgba(255,255,255,0.006) 100%);
  border: 1px solid var(--hue);
  margin: 8px 0 16px 0;
}
.ws-od-weak-head {
  display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
  margin-bottom: 6px;
}
.ws-od-weak-tag {
  padding: 3px 10px; border-radius: 999px;
  background: var(--pill-bg); border: 1px solid var(--hue);
  color: var(--hue); font-size: 10px; font-weight: 800;
  text-transform: uppercase; letter-spacing: 0.10em;
}
.ws-od-weak-name {
  font-size: 15px; color: var(--od-ink); font-weight: 800;
}
.ws-od-weak-score {
  color: var(--hue); font-weight: 900; font-size: 15px; margin-left: auto;
}
.ws-od-weak-reason {
  font-size: 12.5px; color: var(--od-mute); margin-bottom: 10px; line-height: 1.45;
}
.ws-od-swap {
  padding: 10px 12px; border-radius: 12px;
  background: rgba(255,255,255,0.03);
  border: 1px solid var(--od-line);
  margin-bottom: 6px;
}
.ws-od-swap-head { display: flex; align-items: baseline; gap: 8px; margin-bottom: 3px; }
.ws-od-swap-kind {
  padding: 2px 8px; border-radius: 999px;
  background: rgba(255,255,255,0.06); border: 1px solid var(--od-line);
  color: var(--od-ink); font-size: 10px; font-weight: 800;
  text-transform: uppercase; letter-spacing: 0.10em;
}
.ws-od-swap-label { font-size: 13px; color: var(--od-ink); font-weight: 700; }
.ws-od-swap-uplift {
  margin-left: auto;
  color: var(--od-serene); font-weight: 800; font-size: 12px;
}
.ws-od-swap-uplift.negband { color: var(--od-solid); }
.ws-od-swap-detail { font-size: 12px; color: var(--od-mute); line-height: 1.4; }

/* --- Advisory ------------------------------------------------------ */
.ws-od-advisory {
  padding: 14px 16px; border-radius: 14px;
  background: var(--od-glass); border: 1px solid var(--od-line);
  margin: 8px 0 12px 0;
}
.ws-od-advisory ol { margin: 4px 0 0 22px; padding: 0; }
.ws-od-advisory li {
  font-size: 12.5px; color: var(--od-ink); line-height: 1.5; margin-bottom: 4px;
}
.ws-od-advisory li b { color: var(--od-ink); }

/* --- Empty state --------------------------------------------------- */
.ws-od-empty {
  padding: 22px 24px; border-radius: 16px;
  background: linear-gradient(135deg, rgba(123,197,241,0.05) 0%, transparent 100%);
  border: 1px dashed rgba(123,197,241,0.35);
  color: var(--od-mute); font-size: 13.5px; line-height: 1.55;
}
.ws-od-empty b { color: var(--od-ink); }
.ws-od-empty-title {
  font-size: 15px; font-weight: 800; color: var(--od-ink); margin-bottom: 6px;
  letter-spacing: -0.01em;
}

/* --- Drift chart --------------------------------------------------- */
.ws-od-drift {
  display: grid;
  grid-template-columns: 60px 1fr;
  gap: 12px;
  align-items: end;
  padding: 12px 14px; border-radius: 12px;
  background: var(--od-glass); border: 1px solid var(--od-line);
  margin-bottom: 10px;
}
.ws-od-drift-title {
  font-size: 10.5px; color: var(--od-mute);
  text-transform: uppercase; letter-spacing: 0.10em;
  font-weight: 700;
}
.ws-od-drift-bars { display: flex; gap: 4px; align-items: end; height: 60px; }
.ws-od-drift-bar {
  flex: 1 1 0; min-width: 12px;
  border-radius: 4px 4px 2px 2px;
  background: var(--barhue);
  height: var(--h);
  position: relative;
  border: 1px solid var(--od-line);
}
.ws-od-drift-bar::after {
  content: attr(data-lbl);
  position: absolute; bottom: -18px; left: 50%; transform: translateX(-50%);
  font-size: 9.5px; color: var(--od-mute); font-weight: 700; white-space: nowrap;
}
</style>
"""


# Composition weights — mirror `odyssey.STAY_WEIGHT / STOPS_WEIGHT /
# CORRIDOR_WEIGHT` so the composition line reads the same numbers as the
# engine.  Kept as constants in theme.py so the module has no back-import
# to feature code.
_OD_STAY_W = 0.30
_OD_STOPS_W = 0.40
_OD_CORRIDOR_W = 0.30

_ODYSSEY_BAND_HUE = {
    "Serene":   ("#53E3A6", "rgba(83,227,166,0.22)",  "rgba(83,227,166,0.14)"),
    "Solid":    ("#7BC5F1", "rgba(123,197,241,0.22)", "rgba(123,197,241,0.14)"),
    "Bumpy":    ("#F9C440", "rgba(249,196,64,0.22)",  "rgba(249,196,64,0.14)"),
    "Fragile":  ("#FF9F43", "rgba(255,159,67,0.22)",  "rgba(255,159,67,0.14)"),
    "Critical": ("#FF3D60", "rgba(255,61,96,0.24)",   "rgba(255,61,96,0.16)"),
    "Safe":     ("#53E3A6", "rgba(83,227,166,0.22)",  "rgba(83,227,166,0.14)"),
    "Caution":  ("#F9C440", "rgba(249,196,64,0.22)",  "rgba(249,196,64,0.14)"),
    "High Risk":("#FF9F43", "rgba(255,159,67,0.22)",  "rgba(255,159,67,0.14)"),
    "Danger":   ("#FF3D60", "rgba(255,61,96,0.24)",   "rgba(255,61,96,0.16)"),
}


def _od_hue(band: str):
    return _ODYSSEY_BAND_HUE.get(band, ("#8892A6", "rgba(136,146,166,0.20)", "rgba(136,146,166,0.12)"))


def _od_verdict_glyph(verdict: str) -> str:
    return {
        "Serene": "✦", "Solid": "◆", "Bumpy": "▲",
        "Fragile": "◈", "Critical": "◉", "empty": "…",
    }.get(verdict, "◇")


def _od_risk_hue(risk_0_1: float) -> str:
    """Waypoint colour on the leg heat strip. Green → amber → red."""
    r = max(0.0, min(1.0, risk_0_1))
    if r < 0.15: return "#53E3A6"
    if r < 0.30: return "#7BC5F1"
    if r < 0.50: return "#F9C440"
    if r < 0.70: return "#FF9F43"
    return "#FF3D60"


def render_odyssey_empty(hint: str = None) -> None:
    """Placeholder shown when there's no TripReport yet."""
    st.markdown(_ODYSSEY_CSS, unsafe_allow_html=True)
    hint = hint or (
        "Pick your <b>stay</b>, add 1–4 <b>stops per day</b> across 2–7 days, "
        "then press <b>Compose Odyssey</b>. Every day is scored under the same "
        "physics as Safety, Compass and Tempo — no new measurements, no extra "
        "config. The trip verdict is <b>worst-day-weighted</b>, so a single "
        "Fragile day can't hide behind Serene neighbours."
    )
    st.markdown(
        f"""
        <div class="ws-od-empty">
          <div class="ws-od-empty-title">Odyssey — Multi-Day Trip Composer</div>
          {hint}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_odyssey(trip) -> None:
    """Render a `odyssey.TripReport`. Falls back to empty state when None
    or `verdict == "empty"`."""
    if trip is None or getattr(trip, "verdict", "") == "empty":
        render_odyssey_empty()
        return

    st.markdown(_ODYSSEY_CSS, unsafe_allow_html=True)

    hue, glow, pill = _od_hue(trip.verdict)
    pct = max(0, min(100, trip.trip_score))

    # ------------------------------------------------------------ hero
    drift = trip.drift_index
    drift_chip_cls = "pos" if drift > 3 else ("neg" if drift < -3 else "")
    drift_arrow = "↗" if drift > 3 else ("↘" if drift < -3 else "→")
    persistence_chip = (
        f'<span class="ws-od-chip neg">persistence <b>{trip.persistence_streak} d</b></span>'
        if trip.persistence_streak >= 2 else
        f'<span class="ws-od-chip">persistence <b>0</b></span>'
    )
    st.markdown(
        f"""
        <div class="ws-od-hero" style="--hue:{hue};--glow:{glow};">
          <div class="ws-od-ring" style="--hue:{hue};--pct:{pct};--glow:{glow};">
            <div class="ws-od-ring-inner">
              <div class="ws-od-score">{trip.trip_score}<small>/100</small></div>
              <div class="ws-od-verdict">{_esc(trip.verdict)}</div>
            </div>
          </div>
          <div class="ws-od-hero-body">
            <div class="ws-od-pill" style="--pill-bg:{pill};--hue:{hue};">
              ODYSSEY · {_esc(trip.verdict).upper()}
            </div>
            <div class="ws-od-hero-title">
              {trip.n_days}-day trip · mean {trip.mean_day_score:.0f} · min {trip.min_day_score}
            </div>
            <div class="ws-od-hero-blurb">{_esc(trip.verdict_reason)}</div>
            <div class="ws-od-hero-chips">
              <span class="ws-od-chip">stops <b>{trip.total_stops}</b></span>
              <span class="ws-od-chip">distance <b>{trip.total_distance_km:.1f} km</b></span>
              <span class="ws-od-chip">risk-km <b>{trip.total_risk_km:.2f}</b></span>
              <span class="ws-od-chip">ETA <b>{trip.total_eta_min:.0f} min</b></span>
              <span class="ws-od-chip {drift_chip_cls}">drift {drift_arrow} <b>{drift:+.1f}</b></span>
              {persistence_chip}
            </div>
          </div>
          <div class="ws-od-mood" style="--hue:{hue};--glow:{glow};">
            <div class="ws-od-mood-glyph">{_od_verdict_glyph(trip.verdict)}</div>
            <div class="ws-od-mood-name">{_esc(trip.verdict)}</div>
            <div class="ws-od-mood-note">worst-day-weighted</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ------------------------------------------------------------ tiles
    st.markdown(
        f"""
        <div class="ws-od-tiles">
          <div class="ws-od-tile">
            <div class="ws-od-tile-label">Trip score</div>
            <div class="ws-od-tile-value">{trip.trip_score}<span style="font-size:14px;color:var(--od-mute);"> /100</span></div>
            <div class="ws-od-tile-hint">0.6·mean + 0.4·min</div>
          </div>
          <div class="ws-od-tile">
            <div class="ws-od-tile-label">Mean day</div>
            <div class="ws-od-tile-value">{trip.mean_day_score:.1f}</div>
            <div class="ws-od-tile-hint">arith mean across days</div>
          </div>
          <div class="ws-od-tile">
            <div class="ws-od-tile-label">Weakest day</div>
            <div class="ws-od-tile-value">{trip.min_day_score}</div>
            <div class="ws-od-tile-hint">min sets the verdict ceiling</div>
          </div>
          <div class="ws-od-tile">
            <div class="ws-od-tile-label">Drift index</div>
            <div class="ws-od-tile-value">{trip.drift_index:+.1f}</div>
            <div class="ws-od-tile-hint">signed sum of Δ(day, day+1)</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ------------------------------------------------------------ day strip
    st.markdown('<div class="ws-od-section-title">Days</div>', unsafe_allow_html=True)
    day_cards = ['<div class="ws-od-day-strip">']
    for i, dr in enumerate(trip.days, 1):
        d_hue, d_glow, d_pill = _od_hue(dr.day_band)
        stops_chip = f"stops <b>{dr.n_stops}</b>"
        dist_chip = f"km <b>{dr.total_distance_km:.1f}</b>"
        risk_chip = f"risk-km <b>{dr.total_risk_km:.2f}</b>"
        fat_chip = ""
        if dr.fatigue_penalty > 0:
            fat_chip = f'<span class="ws-od-daychip" style="color:{_ODYSSEY_BAND_HUE["Fragile"][0]};border-color:rgba(255,159,67,0.25);">fatigue <b>-{dr.fatigue_penalty:.0f}</b></span>'
        day_cards.append(f"""
            <div class="ws-od-day-card" style="--hue:{d_hue};--glow:{d_glow};--pill-bg:{d_pill};">
              <div class="ws-od-day-head">
                <span class="ws-od-day-num">Day {i}</span>
                <span class="ws-od-day-band">{_esc(dr.day_band)}</span>
              </div>
              <div class="ws-od-day-title">{_esc(dr.day.label)}</div>
              <div class="ws-od-day-date">{_esc(dr.day.date)} · depart {dr.day.depart_hour:02d}:00 · {_esc(dr.day.transit_mode)}</div>
              <div class="ws-od-day-score">{dr.day_score}<small>/100</small></div>
              <div class="ws-od-day-reason">{_esc(dr.reason)}</div>
              <div class="ws-od-day-sub">
                <span class="ws-od-daychip">{stops_chip}</span>
                <span class="ws-od-daychip">{dist_chip}</span>
                <span class="ws-od-daychip">{risk_chip}</span>
                {fat_chip}
              </div>
            </div>
        """)
    day_cards.append('</div>')
    st.markdown("\n".join(day_cards), unsafe_allow_html=True)

    # ------------------------------------------------------------ drift chart
    if trip.n_days >= 2:
        chart_bars: list = []
        # normalise heights against 100 pt scale.
        for i, dr in enumerate(trip.days, 1):
            h = max(4, int(round(dr.day_score * 0.55)))  # px in 60-px chart
            bhue, _, _ = _od_hue(dr.day_band)
            chart_bars.append(
                f'<div class="ws-od-drift-bar" style="--barhue:{bhue};--h:{h}px;" '
                f'data-lbl="D{i} · {dr.day_score}"></div>'
            )
        st.markdown(
            f"""
            <div class="ws-od-drift">
              <div class="ws-od-drift-title">day scores</div>
              <div class="ws-od-drift-bars">{"".join(chart_bars)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ------------------------------------------------------------ weakest link
    if trip.weakest_link is not None:
        w = trip.weakest_link
        w_hue, w_glow, w_pill = _od_hue(w.band)
        st.markdown('<div class="ws-od-section-title">Weakest link</div>', unsafe_allow_html=True)
        swaps_html = ""
        if w.swaps:
            rows = []
            for sw in w.swaps:
                up_cls = "" if sw.expected_uplift_pts >= 5 else "negband"
                tgt = f" → <b>{_esc(sw.target_band)}</b>" if sw.target_band else ""
                rows.append(f"""
                    <div class="ws-od-swap">
                      <div class="ws-od-swap-head">
                        <span class="ws-od-swap-kind">{_esc(sw.kind)}</span>
                        <span class="ws-od-swap-label">{_esc(sw.label)}</span>
                        <span class="ws-od-swap-uplift {up_cls}">+{sw.expected_uplift_pts:.1f} pts{tgt}</span>
                      </div>
                      <div class="ws-od-swap-detail">{_esc(sw.detail)}</div>
                    </div>
                """)
            swaps_html = "\n".join(rows)
        else:
            swaps_html = (
                '<div class="ws-od-swap-detail" style="padding:10px 12px;">'
                'No auto-swap improves this day by more than the minimum uplift. '
                'Re-plan manually via Plan Route + Tempo.</div>'
            )
        st.markdown(
            f"""
            <div class="ws-od-weak" style="--hue:{w_hue};--glow:{w_glow};--pill-bg:{w_pill};">
              <div class="ws-od-weak-head">
                <span class="ws-od-weak-tag">{_esc(w.kind)}</span>
                <span class="ws-od-weak-name">{_esc(w.day_label)} · {_esc(w.leg_label)}</span>
                <span class="ws-od-weak-score">{w.score} <span style="color:var(--od-mute);font-size:11px;font-weight:700;">({_esc(w.band)})</span></span>
              </div>
              <div class="ws-od-weak-reason">{_esc(w.reason)}</div>
              {swaps_html}
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ------------------------------------------------------------ advisory
    if trip.trip_advisory:
        items = "".join(f"<li>{_esc(a)}</li>" for a in trip.trip_advisory)
        st.markdown(
            f"""
            <div class="ws-od-advisory">
              <div style="font-size:11px;color:var(--od-mute);text-transform:uppercase;letter-spacing:.10em;font-weight:800;">
                Advisory — ordered actions
              </div>
              <ol>{items}</ol>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # ------------------------------------------------------------ per-day details (expanders)
    st.markdown('<div class="ws-od-section-title">Per-day breakdown</div>', unsafe_allow_html=True)
    for i, dr in enumerate(trip.days, 1):
        d_hue, d_glow, d_pill = _od_hue(dr.day_band)
        with st.expander(f"Day {i} — {dr.day.label} · {dr.day_score} ({dr.day_band})", expanded=(i == 1)):
            # Stay row
            stay_hue, _, stay_pill = _od_hue(dr.stay_band)
            st.markdown(
                f"""
                <div class="ws-od-detail">
                  <h4>Stay</h4>
                  <div class="ws-od-stop-row" style="--hue:{stay_hue};--pill-bg:{stay_pill};">
                    <div><b>{_esc(dr.day.stay_label)}</b>
                      <div style="color:var(--od-mute);font-size:11px;">({dr.day.stay_lat:.4f}, {dr.day.stay_lon:.4f}) · scored at 20:00</div>
                    </div>
                    <div class="ws-od-leg-mini">score</div>
                    <div class="ws-od-stop-badge">{dr.stay_score} · {_esc(dr.stay_band)}</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if dr.day.stops:
                st.markdown('<div class="ws-od-detail"><h4>Stops</h4>', unsafe_allow_html=True)
                for stop, score, band in zip(dr.day.stops, dr.stop_scores, dr.stop_bands):
                    s_hue, _, s_pill = _od_hue(band)
                    st.markdown(
                        f"""
                        <div class="ws-od-stop-row" style="--hue:{s_hue};--pill-bg:{s_pill};">
                          <div><b>{_esc(stop.label)}</b>
                            <div style="color:var(--od-mute);font-size:11px;">dwell {stop.dwell_min} min · ({stop.lat:.4f}, {stop.lon:.4f})</div>
                          </div>
                          <div class="ws-od-leg-mini">score</div>
                          <div class="ws-od-stop-badge">{score} · {_esc(band)}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                st.markdown('</div>', unsafe_allow_html=True)
            if dr.legs:
                st.markdown('<div class="ws-od-detail"><h4>Corridor legs</h4>', unsafe_allow_html=True)
                for leg in dr.legs:
                    l_band = ("Safe" if leg.min_safety_along >= 80 else
                              "Caution" if leg.min_safety_along >= 60 else
                              "High Risk" if leg.min_safety_along >= 35 else "Danger")
                    l_hue, _, l_pill = _od_hue(l_band)
                    heat_cells = "".join(
                        f'<span style="background:{_od_risk_hue(r)};"></span>'
                        for _, _, r in leg.samples
                    )
                    st.markdown(
                        f"""
                        <div class="ws-od-leg-row" style="--hue:{l_hue};--pill-bg:{l_pill};">
                          <div><b>{_esc(leg.a_label)}</b>
                            <span class="ws-od-leg-arrow">→</span>
                            <b>{_esc(leg.b_label)}</b>
                            <div class="ws-od-leg-strip">{heat_cells}</div>
                          </div>
                          <div><span class="ws-od-leg-mini">dist</span>
                            <div class="ws-od-leg-num">{leg.distance_km:.2f}</div></div>
                          <div><span class="ws-od-leg-mini">ETA</span>
                            <div class="ws-od-leg-num">{leg.eta_min:.0f} m</div></div>
                          <div><span class="ws-od-leg-mini">risk-km</span>
                            <div class="ws-od-leg-num">{leg.risk_km:.2f}</div></div>
                          <div class="ws-od-stop-badge">{leg.min_safety_along}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                st.markdown('</div>', unsafe_allow_html=True)
            # Composition line
            st.markdown(
                f"""
                <div class="ws-od-detail" style="padding:8px 12px;">
                  <div class="ws-od-leg-mini">composition</div>
                  <div style="font-size:12.5px;color:var(--od-ink);margin-top:2px;">
                    {_OD_STAY_W:.2f}·stay ({dr.stay_score}) + {_OD_STOPS_W:.2f}·mean(stops) ({int(round(sum(dr.stop_scores)/max(1,len(dr.stop_scores))))}) + {_OD_CORRIDOR_W:.2f}·corridor ({dr.corridor_score}) − fatigue ({dr.fatigue_penalty:.0f}) = <b>{dr.day_score}</b>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
