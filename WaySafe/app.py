
import streamlit as st
import pandas as pd
import pydeck as pdk
import json, uuid, io, base64, urllib.parse
from datetime import datetime, date, time, timedelta
from pathlib import Path
from PIL import Image

from utils import haversine_km, point_in_polygon, sha256_hex, build_merkle
from safety import compute_safety, heatmap_points
from routing import (
    plan_safest_route, plan_fastest_route,
    plan_forecast_route, find_best_departure, to_gpx,
)
from forecast import HazardForecaster, dow_name
from theme import (
    inject_theme, render_brand, render_score_card, band_color,
    render_route_compare, render_route_summary, ROUTE_ACCENT,
    render_forecast_card, render_24h_curve, render_category_bars,
    render_best_window, render_hotspots, forecast_color,
)

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

st.set_page_config(page_title="WaySafe — Smart Tourism Safety", layout="wide", page_icon="🚦")
inject_theme()

with open(DATA / "goa_geofences.geojson") as f:
    GEOFENCES = json.load(f)

def load_csv(name):
    p = DATA / name
    return pd.read_csv(p) if p.exists() else pd.DataFrame()

def save_csv(df, name):
    df.to_csv(DATA / name, index=False)

inc_df = load_csv("incidents.csv")
bcast_df = load_csv("broadcasts.csv")
poi_df = load_csv("poi.csv")
sos_df = load_csv("sos.csv")

if "user" not in st.session_state:
    st.session_state.user = f"user-{str(uuid.uuid4())[:8]}"
if "outbox" not in st.session_state:
    st.session_state.outbox = []
if "offline" not in st.session_state:
    st.session_state.offline = False
if "sos_active" not in st.session_state:
    st.session_state.sos_active = False
if "current_loc" not in st.session_state:
    st.session_state.current_loc = {"lat": 15.55, "lon": 73.77}


@st.cache_data(show_spinner=False)
def _build_forecaster(rows_json: str, _now_iso: str) -> HazardForecaster:
    rows = json.loads(rows_json)
    return HazardForecaster(rows, now=datetime.fromisoformat(_now_iso))


def get_forecaster() -> HazardForecaster:
    """Build (and cache) the forecaster from the *current* incidents.csv."""
    rows = inc_df.to_dict("records") if not inc_df.empty else []
    payload = json.dumps(rows, default=str)
    return _build_forecaster(payload, datetime.utcnow().isoformat(timespec="minutes"))


with st.sidebar:
    render_brand()
role = st.sidebar.radio(
    "View",
    ["Tourist App", "Authority Dashboard", "Merkle Auditor"],
    label_visibility="collapsed",
)
st.sidebar.caption(f"Session user · `{st.session_state.user}`")

with st.sidebar.expander("Location & Demo Controls", expanded=True):
    st.session_state.offline = st.checkbox("Offline mode (simulate no network)", value=st.session_state.offline)
    lat = st.number_input("Your lat", value=float(st.session_state.current_loc["lat"]), format="%.6f")
    lon = st.number_input("Your lon", value=float(st.session_state.current_loc["lon"]), format="%.6f")
    if st.button("Update location", type="primary", use_container_width=True):
        st.session_state.current_loc = {"lat": lat, "lon": lon}
    st.caption("Tip: 15.55,73.76 (Baga) · 15.49,73.78 (Aguada) · 15.50,73.83 (Panaji)")

with st.sidebar.expander("Map Options"):
    if "show_heatmap" not in st.session_state:
        st.session_state.show_heatmap = True
    st.session_state.show_heatmap = st.checkbox("Incident risk heatmap", value=st.session_state.show_heatmap)


def geofence_hits(lat, lon):
    zones = []
    for feat in GEOFENCES["features"]:
        poly = feat["geometry"]["coordinates"][0]
        if point_in_polygon(lat, lon, poly):
            zones.append(feat["properties"])
    return zones

def push_outbox():
    inc_local = load_csv("incidents.csv")
    applied = 0
    for item in list(st.session_state.outbox):
        if item["type"] == "incident":
            row = item["row"]
            inc_local = pd.concat([inc_local, pd.DataFrame([row])], ignore_index=True)
            st.session_state.outbox.remove(item); applied += 1
        elif item["type"] == "sos":
            row = item["row"]
            s = load_csv("sos.csv")
            s = pd.concat([s, pd.DataFrame([row])], ignore_index=True)
            save_csv(s, "sos.csv")
            st.session_state.outbox.remove(item); applied += 1
    save_csv(inc_local, "incidents.csv")
    return applied


# ---------------- map drawing ----------------

def draw_map_layers(
    incidents, broadcasts, pois, user_loc,
    *, show_heatmap=True,
    extra_layers=None, view_state_override=None,
):
    layers = []
    for feat in GEOFENCES["features"]:
        coords = feat["geometry"]["coordinates"][0]
        name = feat.get("properties", {}).get("name", "Risk zone")
        layers.append(pdk.Layer(
            "PolygonLayer",
            data=[{"polygon": coords, "name": name}],
            get_polygon="polygon",
            get_fill_color=[255, 106, 61, 45],
            get_line_color=[255, 106, 61, 220],
            line_width_min_pixels=1,
            pickable=True,
        ))

    if show_heatmap and not incidents.empty:
        pts = heatmap_points(incidents.to_dict("records"))
        if pts:
            layers.append(pdk.Layer(
                "HeatmapLayer",
                data=pts,
                get_position='[lon, lat]',
                get_weight='weight',
                aggregation='SUM',
                radius_pixels=60,
                opacity=0.55,
            ))

    if not incidents.empty:
        inc_viz = incidents.copy()
        inc_viz["color"] = inc_viz["status"].map(
            lambda s: [255, 61, 96] if s == "verified" else [249, 196, 64]
        )
        layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=inc_viz,
            get_position='[lon, lat]',
            get_fill_color='color',
            get_radius=45,
            pickable=True,
        ))

    if not broadcasts.empty:
        bc = broadcasts.copy()
        bc["radius"] = broadcasts["radius_km"] * 1000
        layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=bc,
            get_position='[lon, lat]',
            get_fill_color=[61, 169, 252, 55],
            get_line_color=[61, 169, 252, 200],
            stroked=True,
            get_radius='radius',
            line_width_min_pixels=1,
        ))

    if not pois.empty:
        layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=pois.assign(size=50),
            get_position='[lon, lat]',
            get_fill_color=[83, 227, 166],
            get_radius=35,
            pickable=True,
        ))

    layers.append(pdk.Layer(
        "ScatterplotLayer",
        data=pd.DataFrame([{"lat": user_loc["lat"], "lon": user_loc["lon"]}]),
        get_position='[lon, lat]',
        get_fill_color=[249, 196, 64],
        get_line_color=[14, 17, 23],
        stroked=True,
        get_radius=60,
        line_width_min_pixels=2,
    ))

    if extra_layers:
        layers.extend(extra_layers)

    view_state = view_state_override or pdk.ViewState(
        latitude=user_loc["lat"], longitude=user_loc["lon"], zoom=12
    )
    tooltip = {
        "html": "<b>{name}</b>{category}{ptype}",
        "style": {"backgroundColor": "#161A23", "color": "#fff", "fontSize": "12px"},
    }
    st.pydeck_chart(pdk.Deck(
        layers=layers,
        initial_view_state=view_state,
        map_style=None,
        tooltip=tooltip,
    ))


def _route_path_layer(route, color_rgb, *, glow_width=8, line_width=4):
    if not route or not route.coords or len(route.coords) < 2:
        return []
    path = [[lon, lat] for lat, lon in route.coords]
    base = pdk.Layer(
        "PathLayer",
        data=[{"path": path}],
        get_path="path",
        get_color=color_rgb,
        get_width=line_width,
        width_min_pixels=line_width,
        rounded=True,
        billboard=False,
    )
    halo_color = color_rgb + [55] if len(color_rgb) == 3 else color_rgb
    halo = pdk.Layer(
        "PathLayer",
        data=[{"path": path}],
        get_path="path",
        get_color=halo_color,
        get_width=glow_width,
        width_min_pixels=glow_width,
        rounded=True,
    )
    return [halo, base]


def _maps_deeplink(coords):
    """Down-sample to ≤9 waypoints and produce a Google Maps deeplink."""
    if not coords or len(coords) < 2:
        return ""
    if len(coords) <= 9:
        pts = coords
    else:
        step = (len(coords) - 1) / 8
        idxs = sorted({0, len(coords) - 1, *[int(round(i * step)) for i in range(9)]})
        pts = [coords[i] for i in idxs]
    waypoints = "/".join(f"{lat:.5f},{lon:.5f}" for lat, lon in pts)
    return f"https://www.google.com/maps/dir/{waypoints}"


# ---------------- views ----------------

if role == "Tourist App":
    st.title("Tourist App")
    my = st.session_state.current_loc

    safety = compute_safety(
        my["lat"], my["lon"],
        incidents=inc_df.to_dict("records") if not inc_df.empty else [],
        geofences=GEOFENCES,
        pois=poi_df.to_dict("records") if not poi_df.empty else [],
    )
    render_score_card(safety)
    if safety.band in ("High Risk", "Danger"):
        st.warning(f"⚠️ {safety.band} zone — review factors above and consider an alternate route.")

    tabs = st.tabs([
        "Map", "Plan Route", "Forecast",
        "Report Hazard", "Alerts", "SOS", "Trip Report",
    ])

    # ---------------- Map
    with tabs[0]:
        draw_map_layers(inc_df, bcast_df, poi_df, my, show_heatmap=st.session_state.show_heatmap)
        st.caption("🔴 verified incident · 🟡 pending · 🟢 help POI · 🟠 risk zone · 🔵 active broadcast")

    # ---------------- Plan Route (long-overdue Day-6 wiring)
    with tabs[1]:
        st.subheader("Plan a Safe Route")
        st.caption(
            "Risk-aware A* — runs **fastest** (α=0) and **safest** (α=4.5) in parallel. "
            "Pick a depart time to fold in the **temporal forecast** for an ETA-aware safest path."
        )

        col_dest, col_depart = st.columns([3, 2])
        with col_dest:
            poi_options = ["— custom lat/lon —"]
            if not poi_df.empty:
                poi_options += [f"{r['name']} · {r['ptype']}" for _, r in poi_df.iterrows()]
            chosen = st.selectbox("Destination", poi_options, index=min(1, len(poi_options)-1))
            if chosen == "— custom lat/lon —":
                cdc1, cdc2 = st.columns(2)
                d_lat = cdc1.number_input("Dest lat", value=15.4966, format="%.6f", key="plan_dest_lat")
                d_lon = cdc2.number_input("Dest lon", value=73.8262, format="%.6f", key="plan_dest_lon")
                dest_label = f"({d_lat:.4f}, {d_lon:.4f})"
            else:
                idx = poi_options.index(chosen) - 1
                row = poi_df.iloc[idx]
                d_lat, d_lon = float(row["lat"]), float(row["lon"])
                dest_label = row["name"]
        with col_depart:
            now = datetime.utcnow()
            d_date = st.date_input("Depart date", value=now.date(), key="plan_depart_date")
            d_time = st.time_input("Depart time", value=now.time().replace(second=0, microsecond=0), key="plan_depart_time")
            depart_at = datetime.combine(d_date, d_time)
            include_forecast = st.checkbox("Use temporal forecast", value=True, key="plan_use_forecast")

        if st.button("Plan routes", type="primary", use_container_width=True):
            origin = (my["lat"], my["lon"])
            dest = (d_lat, d_lon)
            inc_records = inc_df.to_dict("records") if not inc_df.empty else []
            poi_records = poi_df.to_dict("records") if not poi_df.empty else []
            with st.spinner("Searching grid (A* over priced edges)…"):
                fastest = plan_fastest_route(origin, dest, inc_records, GEOFENCES, poi_records, now=depart_at)
                safest  = plan_safest_route(origin, dest, inc_records, GEOFENCES, poi_records, now=depart_at)
                forecast_route = None
                if include_forecast:
                    forecaster = get_forecaster()
                    forecast_route = plan_forecast_route(
                        origin, dest, forecaster, depart_at,
                        incidents=inc_records, geofences=GEOFENCES, pois=poi_records,
                    )
            st.session_state.plan = {
                "fastest": fastest, "safest": safest, "forecast": forecast_route,
                "origin": origin, "dest": dest, "dest_label": dest_label,
                "depart_at": depart_at,
            }

        plan = st.session_state.get("plan")
        if plan:
            fastest, safest = plan["fastest"], plan["safest"]
            forecast_route = plan.get("forecast")

            render_route_summary(safest, fastest)
            render_route_compare(safest, fastest)

            if forecast_route is not None:
                st.markdown(
                    f"<div class='ws-fc-meta-label' style='margin-top:8px;'>Forecast-aware (departs "
                    f"{plan['depart_at'].strftime('%a %H:%M')} · arrives "
                    f"{forecast_route.arrive_at.strftime('%H:%M')})</div>",
                    unsafe_allow_html=True,
                )
                cs1, cs2, cs3, cs4 = st.columns(4)
                cs1.metric("Distance", f"{forecast_route.distance_km:g} km")
                cs2.metric("Avg safety", forecast_route.avg_safety,
                           delta=int(forecast_route.avg_safety - fastest.avg_safety))
                cs3.metric("Min safety", forecast_route.min_safety)
                cs4.metric("Risk km", f"{forecast_route.max_risk_segment_km:g}")
                if forecast_route.notes:
                    st.caption(" · ".join(forecast_route.notes))

            # Map: dual route overlay (+ forecast route purple if present)
            extras = []
            extras += _route_path_layer(safest,   [61, 169, 252])         # cyan
            extras += _route_path_layer(fastest,  [249, 196, 64])         # amber
            if forecast_route is not None:
                extras += _route_path_layer(forecast_route, [167, 139, 250], glow_width=10)
            origin_lat, origin_lon = plan["origin"]; dest_lat, dest_lon = plan["dest"]
            mid_lat = (origin_lat + dest_lat) / 2; mid_lon = (origin_lon + dest_lon) / 2
            view = pdk.ViewState(latitude=mid_lat, longitude=mid_lon, zoom=12)
            extras.append(pdk.Layer(
                "ScatterplotLayer",
                data=pd.DataFrame([
                    {"lat": origin_lat, "lon": origin_lon, "name": "Start"},
                    {"lat": dest_lat,   "lon": dest_lon,   "name": plan["dest_label"]},
                ]),
                get_position='[lon, lat]',
                get_fill_color=[83, 227, 166],
                get_radius=70,
                pickable=True,
                stroked=True, get_line_color=[14, 17, 23], line_width_min_pixels=2,
            ))
            draw_map_layers(
                inc_df, bcast_df, poi_df, my,
                show_heatmap=False,
                extra_layers=extras,
                view_state_override=view,
            )
            legend = (
                "🟦 Safest path · 🟧 Fastest path"
                + (" · 🟪 Forecast-aware" if forecast_route is not None else "")
                + " · 🟢 Start/End"
            )
            st.caption(legend)

            # GPX downloads + Maps deeplinks
            cdl1, cdl2, cdl3, cdl4 = st.columns(4)
            cdl1.download_button(
                "Safest route GPX",
                data=to_gpx(safest, name=f"WaySafe safest → {plan['dest_label']}"),
                file_name=f"waysafe-safest.gpx", mime="application/gpx+xml",
                use_container_width=True,
            )
            cdl2.download_button(
                "Fastest route GPX",
                data=to_gpx(fastest, name=f"WaySafe fastest → {plan['dest_label']}"),
                file_name=f"waysafe-fastest.gpx", mime="application/gpx+xml",
                use_container_width=True,
            )
            cdl3.markdown(
                f"<a href='{_maps_deeplink(safest.coords)}' target='_blank' "
                f"style='display:block; text-align:center; padding:9px 12px; border-radius:10px; "
                f"background:rgba(61,169,252,0.18); color:#3DA9FC; font-weight:700; "
                f"text-decoration:none; border:1px solid rgba(61,169,252,0.36);'>"
                f"Open safest in Maps ↗</a>",
                unsafe_allow_html=True,
            )
            cdl4.markdown(
                f"<a href='{_maps_deeplink(fastest.coords)}' target='_blank' "
                f"style='display:block; text-align:center; padding:9px 12px; border-radius:10px; "
                f"background:rgba(249,196,64,0.18); color:#F9C440; font-weight:700; "
                f"text-decoration:none; border:1px solid rgba(249,196,64,0.36);'>"
                f"Open fastest in Maps ↗</a>",
                unsafe_allow_html=True,
            )

            # Best-departure window optimiser
            with st.expander("🔮 Find best departure window (forecast-aware sweep ±2 h)"):
                if st.button("Search ±2 hours at 30-min steps"):
                    forecaster = get_forecaster()
                    inc_records = inc_df.to_dict("records") if not inc_df.empty else []
                    poi_records = poi_df.to_dict("records") if not poi_df.empty else []
                    with st.spinner("Sweeping 9 candidate departures…"):
                        windows = find_best_departure(
                            plan["origin"], plan["dest"], forecaster, plan["depart_at"],
                            incidents=inc_records, geofences=GEOFENCES, pois=poi_records,
                            span_h=2.0, step_min=30,
                        )
                    render_best_window(windows, plan["depart_at"])

    # ---------------- Forecast
    with tabs[2]:
        st.subheader("Hazard Forecast")
        st.caption(
            "Empirical-Bayes spatiotemporal model — historical hazards binned by "
            "(½ km cell × DOW × hour), kernel-smoothed across the 3 × 3 time neighbourhood, "
            "Poisson-saturated to a 0–100 risk."
        )

        forecaster = get_forecaster()
        summ = forecaster.summary()

        cc1, cc2 = st.columns([3, 2])
        with cc1:
            mode = st.radio("Time", ["Now", "Custom"], horizontal=True, label_visibility="collapsed")
        with cc2:
            if mode == "Custom":
                f_date = st.date_input("Forecast date", value=date.today() + timedelta(days=1),
                                       key="fc_date")
                f_hour = st.slider("Hour of day", 0, 23, value=22, key="fc_hour")
                when = datetime.combine(f_date, time(hour=f_hour))
            else:
                when = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
                st.caption(f"Forecasting for **{when.strftime('%a %d %b · %H:%M')} UTC**")

        # headline forecast at user location
        fc_here = forecaster.forecast(my["lat"], my["lon"], when)
        render_forecast_card(fc_here, when, location_label="your location")

        # 24-h curve + categories side by side
        ccol1, ccol2 = st.columns([3, 2])
        with ccol1:
            curve = forecaster.risk_curve(my["lat"], my["lon"], when)
            render_24h_curve(
                curve,
                label=f"24-hour risk · {dow_name(when.weekday())} at your location",
            )
            st.caption(
                f"Peak hour today: **{curve.index(max(curve)) if max(curve) > 0 else 'flat'}:00** · "
                f"trough: **{curve.index(min(curve)):02d}:00**"
            )
        with ccol2:
            render_category_bars(fc_here.top_categories, label="Expected category mix")
            sm1, sm2 = st.columns(2)
            sm1.metric("Trained on", f"{summ['incidents_trained']} incidents")
            sm2.metric("Cells learned", summ['cells'])
            if summ.get("peak_hour") is not None:
                st.caption(
                    f"City peak hour: **{summ['peak_hour']:02d}:00** · "
                    f"peak day: **{dow_name(summ['peak_dow'])}** · "
                    f"top hazards: " +
                    ", ".join(c for c, _ in summ.get("top_categories", [])[:2])
                )

        # Forecast heatmap on the map — tight bbox around the user (~7 km radius)
        # so the lattice resolves at ~250m cells and the colour ramp lights up.
        rad = 0.06  # ≈ 6.5 km in lat
        bbox = (my["lat"] - rad, my["lon"] - rad,
                my["lat"] + rad, my["lon"] + rad)
        grid_pts = forecaster.risk_grid(when=when, bbox=bbox, n=48)
        forecast_layer = []
        if grid_pts:
            df_grid = pd.DataFrame(grid_pts, columns=["lat", "lon", "risk"])
            forecast_layer.append(pdk.Layer(
                "HeatmapLayer",
                data=df_grid.to_dict("records"),
                get_position='[lon, lat]',
                get_weight='risk',
                aggregation='SUM',
                radius_pixels=70,
                opacity=0.7,
                color_range=[
                    [83, 227, 166, 0],
                    [83, 227, 166, 90],
                    [249, 196, 64, 130],
                    [255, 127, 80, 170],
                    [255, 61, 96, 220],
                    [167, 139, 250, 240],
                ],
            ))
        st.markdown("**Forecast heatmap** — predicted hazard intensity at the chosen time")
        draw_map_layers(
            inc_df, bcast_df, poi_df, my,
            show_heatmap=False,
            extra_layers=forecast_layer,
        )

        # Tomorrow's hotspots
        st.markdown("---")
        hs = forecaster.hotspots(when, k=5)
        render_hotspots(hs, label=f"Top forecasted hotspots · {when.strftime('%a %H:%M')}")
        if hs:
            top = hs[0]
            st.caption(
                f"Most-elevated cell at this time is centred near "
                f"({top['lat']:.4f}, {top['lon']:.4f}) — historically dominated by "
                f"**{top['top_category']}**."
            )

    # ---------------- Report Hazard
    with tabs[3]:
        st.subheader("Report a Hazard")
        category = st.selectbox("Category", ["landslide","roadblock","accident","flooding","other"])
        note = st.text_area("Note (optional)")
        up = st.file_uploader("Photo (optional)", type=["jpg","jpeg","png"])
        if st.button("Submit (respects Offline mode)"):
            r_lat = st.session_state.current_loc["lat"]; r_lon = st.session_state.current_loc["lon"]
            ts = datetime.utcnow().isoformat()
            photo_path = ""; sha = ""
            if up:
                img = Image.open(up).convert("RGB")
                img_id = f"{uuid.uuid4().hex[:10]}.jpg"
                p = DATA / "uploads"; p.mkdir(exist_ok=True); img.save(p / img_id, "JPEG", quality=70, optimize=True)
                photo_path = f"data/uploads/{img_id}"
                with open(p / img_id, "rb") as fh:
                    sha = sha256_hex(fh.read() + f"{r_lat}{r_lon}{ts}".encode())
            else:
                sha = sha256_hex(f"{r_lat}{r_lon}{ts}".encode())
            row = {"id": str(uuid.uuid4()), "user": st.session_state.user, "lat": r_lat, "lon": r_lon,
                   "category": category, "note": note, "photo_path": photo_path, "sha256": sha,
                   "sig": f"sig-{st.session_state.user[:6]}", "status": "pending", "created_at": ts}
            if st.session_state.offline:
                st.session_state.outbox.append({"type": "incident", "row": row}); st.info("Saved offline (Queued • 1). Turn off Offline mode and click Sync.")
            else:
                inc_local = load_csv("incidents.csv")
                inc_local = pd.concat([inc_local, pd.DataFrame([row])], ignore_index=True); save_csv(inc_local, "incidents.csv")
                st.success("Incident submitted!")
                inc_df = load_csv("incidents.csv")
        if st.button("Sync now"):
            applied = push_outbox()
            if applied: st.success(f"Synced {applied} queued items."); inc_df = load_csv("incidents.csv")

    # ---------------- Alerts
    with tabs[4]:
        st.subheader("Broadcast Alerts near you")
        my2 = st.session_state.current_loc
        if bcast_df.empty:
            st.info("No alerts yet.")
        else:
            nearby = []
            for _, r in bcast_df.iterrows():
                d = haversine_km(my2["lat"], my2["lon"], r["lat"], r["lon"])
                if d <= r["radius_km"]:
                    nearby.append(r)
            if nearby:
                for r in nearby:
                    st.error(f"ALERT: Verified {r['incident_id'][:6]} • within {r['radius_km']} km")
            else:
                st.success("No active alerts in your radius.")
        st.caption("Simulated WS via file updates.")

    # ---------------- SOS
    with tabs[5]:
        st.subheader("SOS")
        col1, col2 = st.columns(2)
        with col1:
            if not st.session_state.sos_active:
                if st.button("Start SOS"):
                    st.session_state.sos_active = True
                    row = {"sos_id": str(uuid.uuid4()), "user": st.session_state.user,
                           "lat": st.session_state.current_loc["lat"], "lon": st.session_state.current_loc["lon"],
                           "active": True, "ts": datetime.utcnow().isoformat()}
                    if st.session_state.offline:
                        st.session_state.outbox.append({"type":"sos","row":row})
                    else:
                        s = load_csv("sos.csv"); s = pd.concat([s, pd.DataFrame([row])], ignore_index=True); save_csv(s, "sos.csv")
                    st.success("SOS started (demo).")
            else:
                if st.button("Stop SOS"):
                    st.session_state.sos_active = False; st.warning("SOS stopped (demo).")
        with col2:
            my3 = st.session_state.current_loc
            def _dist(row):
                return haversine_km(my3["lat"], my3["lon"], row["lat"], row["lon"])
            poi_local = load_csv("poi.csv")
            poi_local["dist_km"] = poi_local.apply(_dist, axis=1)
            st.write("Nearest help:"); st.table(poi_local.sort_values("dist_km").head(3)[["name","ptype","dist_km"]])

    # ---------------- Trip Report
    with tabs[6]:
        st.subheader("Export Trip (demo)")
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import cm
        if st.button("Generate PDF"):
            buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=A4)
            w,h = A4; c.setFont("Helvetica-Bold",14); c.drawString(2*cm,h-2*cm,"Trip & Safety Report (POC)")
            c.setFont("Helvetica",10); c.drawString(2*cm,h-2.7*cm,f"User: {st.session_state.user}  | Generated: {datetime.utcnow().isoformat()}Z")
            inc_mine = inc_df[inc_df["user"] == st.session_state.user].tail(5); y = h-3.5*cm
            for _, r in inc_mine.iterrows():
                c.drawString(2*cm,y,f"- {r['created_at'][:19]}Z • {r['category']} @ ({r['lat']:.4f},{r['lon']:.4f}) • status={r['status']}"); y -= 0.7*cm
            c.showPage(); c.save(); buf.seek(0)
            b64 = base64.b64encode(buf.read()).decode()
            st.markdown(f'<a download="trip_report.pdf" href="data:application/pdf;base64,{b64}">Download Trip PDF</a>', unsafe_allow_html=True)

elif role == "Authority Dashboard":
    st.title("Authority Dashboard")
    verified_n = int((inc_df["status"] == "verified").sum()) if not inc_df.empty else 0
    pending_n = int((inc_df["status"] == "pending").sum()) if not inc_df.empty else 0
    active_sos = len(sos_df[sos_df["active"] == True]) if not sos_df.empty else 0
    colA, colB, colC, colD = st.columns(4)
    colA.metric("Incidents", len(inc_df))
    colB.metric("Verified", verified_n)
    colC.metric("Pending", pending_n)
    colD.metric("Active SOS", active_sos)

    if not inc_df.empty:
        left, right = st.columns([1, 1])
        with left:
            st.markdown('<div class="ws-kicker">Incidents by category</div>', unsafe_allow_html=True)
            st.bar_chart(inc_df["category"].value_counts(), height=220)
        with right:
            st.markdown('<div class="ws-kicker">Incidents over time</div>', unsafe_allow_html=True)
            try:
                ts = pd.to_datetime(inc_df["created_at"], errors="coerce").dropna()
                if not ts.empty:
                    daily = ts.dt.floor("D").value_counts().sort_index()
                    st.line_chart(daily, height=220)
                else:
                    st.caption("No timestamps available.")
            except Exception:
                st.caption("No timestamps available.")

    # NEW: Forecasted hotspots — next 24h
    st.markdown("---")
    st.subheader("Forecast — next 24 hours")
    forecaster = get_forecaster()
    cf1, cf2 = st.columns([3, 2])
    with cf1:
        next_hours = []
        base = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
        for k in range(24):
            t = base + timedelta(hours=k)
            hs = forecaster.hotspots(t, k=1)
            top_risk = hs[0]["risk"] if hs else 0.0
            next_hours.append(top_risk)
        peak_idx = next_hours.index(max(next_hours)) if next_hours else 0
        peak_t = base + timedelta(hours=peak_idx)
        st.markdown(
            f"**Peak forecast risk in the next 24 h:** "
            f"<span style='color:{forecast_color(next_hours[peak_idx])}; font-weight:700;'>"
            f"{int(next_hours[peak_idx]*100)}</span> · "
            f"{peak_t.strftime('%a %H:%M')} UTC",
            unsafe_allow_html=True,
        )
        render_24h_curve(next_hours, label="Top-cell risk per hour · next 24 h")
    with cf2:
        peak_window = base + timedelta(hours=peak_idx)
        hotspots_at_peak = forecaster.hotspots(peak_window, k=4)
        render_hotspots(
            hotspots_at_peak,
            label=f"Likely hotspots at peak ({peak_window.strftime('%a %H:%M')})",
        )

    st.subheader("Operational Map")
    draw_map_layers(inc_df, bcast_df, poi_df, {"lat": 15.51, "lon": 73.83}, show_heatmap=True)

    st.subheader("Pending Incidents")
    pending = inc_df[inc_df["status"]=="pending"]
    if pending.empty:
        st.info("No pending incidents.")
    else:
        for _, r in pending.iterrows():
            with st.container(border=True):
                st.write(f"**{r['category']}** • {r['created_at']} • ({r['lat']:.4f},{r['lon']:.4f})")
                if r["photo_path"]:
                    try: st.image(str(ROOT / r["photo_path"]), width=220, caption="Evidence")
                    except: st.caption("Photo available (path).")
                col1, col2 = st.columns(2)
                if col1.button("Verify", key=f"v-{r['id']}"):
                    inc_local = load_csv("incidents.csv"); inc_local.loc[inc_local["id"]==r["id"], "status"] = "verified"
                    save_csv(inc_local, "incidents.csv"); st.success("Verified."); inc_df = load_csv("incidents.csv")
                radius = col2.slider("Broadcast radius (km)", 1.0, 10.0, 3.0, key=f"rad-{r['id']}")
                if st.button("Broadcast", key=f"b-{r['id']}"):
                    bc_row = {"id": str(uuid.uuid4()), "incident_id": r["id"], "lat": r["lat"], "lon": r["lon"],
                              "radius_km": radius, "created_at": datetime.utcnow().isoformat()}
                    b = load_csv("broadcasts.csv"); b = pd.concat([b, pd.DataFrame([bc_row])], ignore_index=True); save_csv(b, "broadcasts.csv")
                    st.success("Broadcast sent (sim)."); bcast_df = load_csv("broadcasts.csv")

    st.subheader("SOS Monitor"); st.dataframe(sos_df.tail(10))

elif role == "Merkle Auditor":
    st.title("Merkle Rollup Auditor")
    st.caption("Build a Merkle root from current incident hashes to prove tamper-evidence.")
    if st.button("Build Merkle Now"):
        leaves = inc_df["sha256"].dropna().tolist() if not inc_df.empty else []
        root, proofs = build_merkle(leaves)
        if not root: st.info("No leaves to roll up.")
        else:
            st.success(f"Root: {root[:16]}...")
            st.json({k[:10]+'...': v[:4] for k,v in proofs.items()})
    st.write("✅ Tamper-evident without blockchain. Anchor roots on-chain later if needed.")
