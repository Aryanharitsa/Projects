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
