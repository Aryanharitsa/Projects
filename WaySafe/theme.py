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
    "fastest": "#F9C440",
    "safest":  "#3DA9FC",
}


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
