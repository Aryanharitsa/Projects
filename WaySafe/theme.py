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
