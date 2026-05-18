
import streamlit as st
import pandas as pd
import pydeck as pdk
import json, uuid, io, base64, urllib.parse, time as _time
from datetime import datetime, date, time, timedelta
from pathlib import Path
from PIL import Image

from utils import haversine_km, point_in_polygon, sha256_hex, build_merkle
from safety import compute_safety, heatmap_points, point_risk
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
    render_live_trip_header, render_alert_feed, render_lookahead_panel,
    render_contacts_strip, render_broadcast_log, render_trip_empty,
    render_trip_log_row,
    render_itinerary_empty, render_itinerary_summary,
    render_itinerary_timeline, render_itinerary_legs,
    render_itinerary_windows,
    render_sentinel_pulse, render_sentinel_clusters, render_sentinel_empty,
    render_sentinel_watch_banner,
)
import companion as cp
import itinerary as itn
import sentinel as sn

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
if "trip" not in st.session_state:
    st.session_state.trip = None
if "trip_log" not in st.session_state:
    st.session_state.trip_log = []
if "trip_broadcasts" not in st.session_state:
    st.session_state.trip_broadcasts = []
if "trip_auto_advance" not in st.session_state:
    st.session_state.trip_auto_advance = False
if "trip_speed_factor" not in st.session_state:
    st.session_state.trip_speed_factor = 4.0
if "contacts" not in st.session_state:
    p = DATA / "contacts.csv"
    st.session_state.contacts = cp.load_contacts(p) if p.exists() else []


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

    # ---------------- Sentinel: shared cluster computation (Day 26)
    # Computed once per rerun and used by both the Map watch-banner and the
    # full Sentinel tab so the two surfaces never disagree.
    if "sentinel_params" not in st.session_state:
        st.session_state.sentinel_params = {
            "eps_km": sn.DEFAULT_EPS_KM,
            "min_samples": sn.DEFAULT_MIN_SAMPLES,
            "recent_days": 30,
            "baseline_days": 60,
        }
    _sp = st.session_state.sentinel_params
    _inc_records = inc_df.to_dict("records") if not inc_df.empty else []
    sent_clusters, sent_noise = sn.cluster_incidents(
        _inc_records,
        eps_km=_sp["eps_km"], min_samples=_sp["min_samples"],
        recent_days=_sp["recent_days"], baseline_days=_sp["baseline_days"],
    )
    sent_pulse = sn.compute_risk_pulse(
        sent_clusters, _inc_records,
        recent_days=_sp["recent_days"], baseline_days=_sp["baseline_days"],
    )

    tab_labels = [
        "Map", "Plan Route", "Itinerary", "Live Trip", "Forecast",
        "Sentinel", "Report Hazard", "Alerts", "SOS", "Trip Log",
    ]
    tabs = st.tabs(tab_labels)

    # ---------------- Map
    with tabs[0]:
        render_sentinel_watch_banner(sent_pulse)
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

    # ---------------- Itinerary (Day-21 move) ----------------
    with tabs[2]:
        st.subheader("Multi-Stop Itinerary")
        st.caption(
            "String multiple stops into a single safety-aware day. "
            "Order is optimised with a 2-opt over the haversine distance matrix, "
            "each leg is priced by the same risk-aware A* used for single routes, "
            "and the schedule rolls up into a Gantt timeline + iCal export."
        )

        # Default Goa-friendly tour, seeded once per session.
        if "itin_stops_df" not in st.session_state:
            st.session_state.itin_stops_df = pd.DataFrame([
                {"name": "Start (you)",      "lat": my["lat"], "lon": my["lon"], "dwell_min": 0},
                {"name": "Aguada Fort",       "lat": 15.4925,   "lon": 73.7825,   "dwell_min": 45},
                {"name": "Calangute Beach",   "lat": 15.5440,   "lon": 73.7553,   "dwell_min": 60},
                {"name": "Anjuna Flea Market","lat": 15.5736,   "lon": 73.7407,   "dwell_min": 45},
                {"name": "Baga Beach",        "lat": 15.5560,   "lon": 73.7515,   "dwell_min": 30},
            ])

        with st.expander("✏️  Edit stops", expanded=True):
            edited = st.data_editor(
                st.session_state.itin_stops_df,
                num_rows="dynamic",
                use_container_width=True,
                hide_index=True,
                column_config={
                    "name":      st.column_config.TextColumn("Stop", required=True),
                    "lat":       st.column_config.NumberColumn("Lat", format="%.6f", min_value=-90.0, max_value=90.0),
                    "lon":       st.column_config.NumberColumn("Lon", format="%.6f", min_value=-180.0, max_value=180.0),
                    "dwell_min": st.column_config.NumberColumn("Dwell (min)", min_value=0, max_value=600, step=5),
                },
                key="itin_stops_editor",
            )
            # persist
            st.session_state.itin_stops_df = edited
            cset1, cset2 = st.columns(2)
            if cset1.button("Reset first stop to my location", use_container_width=True):
                df = st.session_state.itin_stops_df.copy()
                if not df.empty:
                    df.loc[df.index[0], ["lat", "lon"]] = [my["lat"], my["lon"]]
                    st.session_state.itin_stops_df = df
                    st.rerun()
            if cset2.button("Clear all & start fresh", use_container_width=True):
                st.session_state.itin_stops_df = pd.DataFrame([
                    {"name": "Start (you)", "lat": my["lat"], "lon": my["lon"], "dwell_min": 0},
                ])
                st.rerun()

        c_mode, c_dt, c_opt = st.columns([2, 2, 1.4])
        with c_mode:
            mode = st.selectbox(
                "Routing mode",
                ["safest", "forecast-safest", "fastest"],
                index=0, key="itin_mode",
            )
        with c_dt:
            _now = datetime.utcnow()
            i_date = st.date_input("Depart date", value=_now.date(), key="itin_date")
            i_time = st.time_input("Depart time", value=_now.time().replace(second=0, microsecond=0), key="itin_time")
            i_depart = datetime.combine(i_date, i_time)
        with c_opt:
            st.write("")
            st.write("")
            optimize_order = st.checkbox("Optimize order", value=True, key="itin_opt")

        if st.button("Plan itinerary", type="primary", use_container_width=True, key="itin_plan_btn"):
            df = st.session_state.itin_stops_df.dropna(subset=["lat", "lon"]).copy()
            df["name"] = df["name"].fillna("Stop").astype(str)
            df["dwell_min"] = df["dwell_min"].fillna(0).astype(int)
            stops = [
                itn.Stop(
                    name=str(r["name"]).strip() or f"Stop {i+1}",
                    lat=float(r["lat"]),
                    lon=float(r["lon"]),
                    dwell_min=int(r["dwell_min"]),
                )
                for i, (_, r) in enumerate(df.iterrows())
            ]
            if len(stops) < 2:
                st.error("Add at least 2 stops to plan an itinerary.")
            else:
                inc_records = inc_df.to_dict("records") if not inc_df.empty else []
                poi_records = poi_df.to_dict("records") if not poi_df.empty else []
                forecaster_obj = get_forecaster() if mode == "forecast-safest" else None
                with st.spinner(f"Planning {len(stops)-1} legs in {mode} mode…"):
                    plan_obj = itn.plan_itinerary(
                        stops, i_depart, mode=mode, optimize_order=optimize_order,
                        incidents=inc_records, geofences=GEOFENCES, pois=poi_records,
                        forecaster=forecaster_obj,
                    )
                st.session_state.itinerary = plan_obj

        itinerary = st.session_state.get("itinerary")
        if itinerary is None:
            render_itinerary_empty()
        else:
            render_itinerary_summary(itinerary)
            render_itinerary_timeline(itinerary)

            # Combined map: each leg in a distinct accent
            palette = [
                [61, 169, 252], [167, 139, 250], [249, 196, 64],
                [83, 227, 166], [255, 106, 61], [94, 234, 212],
                [255, 121, 198], [126, 231, 218],
            ]
            extras = []
            for i, leg in enumerate(itinerary.legs):
                color = palette[i % len(palette)]
                extras += _route_path_layer(leg.route, color, glow_width=8, line_width=3)
            stop_df = pd.DataFrame([
                {"lat": s.lat, "lon": s.lon, "name": f"{i+1}. {s.name}"}
                for i, s in enumerate(itinerary.stops)
            ])
            extras.append(pdk.Layer(
                "ScatterplotLayer",
                data=stop_df,
                get_position='[lon, lat]',
                get_fill_color=[83, 227, 166],
                get_radius=85,
                pickable=True,
                stroked=True, get_line_color=[14, 17, 23], line_width_min_pixels=2,
            ))
            extras.append(pdk.Layer(
                "TextLayer",
                data=stop_df,
                get_position='[lon, lat]',
                get_text='name',
                get_size=12,
                get_color=[230, 236, 247],
                get_pixel_offset=[0, -18],
                billboard=False,
            ))
            mid_lat = sum(s.lat for s in itinerary.stops) / len(itinerary.stops)
            mid_lon = sum(s.lon for s in itinerary.stops) / len(itinerary.stops)
            view = pdk.ViewState(latitude=mid_lat, longitude=mid_lon, zoom=11.5)
            draw_map_layers(
                inc_df, bcast_df, poi_df, my,
                show_heatmap=False, extra_layers=extras, view_state_override=view,
            )
            st.caption(
                "🟢 Stops (numbered in visit order) · coloured polylines = per-leg routes · "
                "🔴 verified incident · 🟠 risk zone"
            )

            # Per-leg detail cards
            st.markdown("##### Legs")
            render_itinerary_legs(itinerary)

            # Exports
            cdl1, cdl2, cdl3 = st.columns(3)
            cdl1.download_button(
                "Itinerary GPX",
                data=itn.to_combined_gpx(itinerary, name=f"WaySafe itinerary · {i_depart.strftime('%a %H:%M')}"),
                file_name="waysafe-itinerary.gpx",
                mime="application/gpx+xml",
                use_container_width=True,
            )
            cdl2.download_button(
                "Itinerary iCal (.ics)",
                data=itn.to_ics(itinerary),
                file_name="waysafe-itinerary.ics",
                mime="text/calendar",
                use_container_width=True,
            )
            # Google Maps deeplink across all legs concatenated (down-sampled)
            combined_coords = []
            for leg in itinerary.legs:
                if combined_coords and leg.route.coords:
                    combined_coords.extend(leg.route.coords[1:])
                else:
                    combined_coords.extend(leg.route.coords)
            cdl3.markdown(
                f"<a href='{_maps_deeplink(combined_coords)}' target='_blank' "
                f"style='display:block; text-align:center; padding:9px 12px; border-radius:10px; "
                f"background:rgba(83,227,166,0.18); color:#53E3A6; font-weight:700; "
                f"text-decoration:none; border:1px solid rgba(83,227,166,0.36);'>"
                f"Open full route in Maps ↗</a>",
                unsafe_allow_html=True,
            )

            # Best start-window sweep
            with st.expander("🔮 Find best start window (sweep ±2 h, full re-plan per candidate)"):
                if st.button("Search ±2 hours at 30-min steps", key="itin_sweep_btn"):
                    inc_records = inc_df.to_dict("records") if not inc_df.empty else []
                    poi_records = poi_df.to_dict("records") if not poi_df.empty else []
                    forecaster_obj = get_forecaster() if itinerary.mode == "forecast-safest" else None
                    with st.spinner("Re-planning the whole itinerary at 9 candidate departures…"):
                        windows = itn.find_best_start_window(
                            itinerary.stops, itinerary.depart_at,
                            mode=itinerary.mode, span_h=2.0, step_min=30,
                            incidents=inc_records, geofences=GEOFENCES, pois=poi_records,
                            forecaster=forecaster_obj, optimize_order=False,
                        )
                    render_itinerary_windows(windows, itinerary.depart_at, top_k=5)
                    best_t, best_plan = windows[0]
                    if best_t != itinerary.depart_at:
                        st.info(
                            f"Best start: **{best_t.strftime('%a %H:%M')}** "
                            f"(score {best_plan.composite_score}, "
                            f"+{best_plan.composite_score - itinerary.composite_score} vs your pick). "
                            "Click *Plan itinerary* with this depart time to switch."
                        )
                    else:
                        st.success("Your chosen depart time is already optimal in this window.")

    # ---------------- Live Trip Companion (round-3 closer)
    with tabs[3]:
        st.subheader("Live Trip Companion")
        st.caption(
            "Be *with* the user during the trip — proactive geofence + risk-corridor alerts, "
            "trusted-contact broadcasts, and an auto-SOS rule when stalled in elevated-risk territory."
        )

        plan = st.session_state.get("plan")
        trip = st.session_state.get("trip")

        # Auto-tick on every Streamlit rerun while active (engine reads wall-clock).
        if trip is not None and trip.status == "active":
            inc_rec = inc_df.to_dict("records") if not inc_df.empty else []
            poi_rec = poi_df.to_dict("records") if not poi_df.empty else []
            new_alerts = cp.tick(trip, incidents=inc_rec, geofences=GEOFENCES, pois=poi_rec)
            for a in new_alerts:
                br = cp.dispatch_broadcasts(
                    a, trip, st.session_state.contacts,
                    log_path=DATA / "notifications.csv",
                )
                st.session_state.trip_broadcasts.extend(br)
            if trip.status == "completed":
                st.session_state.trip_log.append(cp.trip_digest(trip))

        # ---- HEADER ----
        if trip is not None:
            render_live_trip_header(trip, datetime.utcnow())
        elif plan is not None:
            st.markdown(
                "<div class='ws-card' style='display:flex; align-items:center; gap:14px;'>"
                "<span style='font-size:1.6rem;'>🚀</span>"
                "<div><div style='font-weight:800; font-size:1.05rem;'>Route ready — start the journey</div>"
                f"<div style='font-size:.82rem; color:#8892A6;'>"
                f"{plan['origin'][0]:.4f},{plan['origin'][1]:.4f} → {plan.get('dest_label','destination')}"
                f" · {plan['safest'].distance_km:g} km · ETA {plan['safest'].eta_minutes:g} min</div></div></div>",
                unsafe_allow_html=True,
            )
        else:
            render_trip_empty()

        # ---- CONTROLS BAR ----
        ctrl_l, ctrl_r = st.columns([3, 2])
        with ctrl_l:
            if trip is None and plan is not None:
                mode_pick = st.radio(
                    "Use which planned route as the live journey?",
                    ["safest", "fastest"] + (["forecast-safest"] if plan.get("forecast") else []),
                    index=0, horizontal=True, key="trip_mode_pick",
                )
                speed = st.select_slider(
                    "Simulation speed",
                    options=[1.0, 2.0, 4.0, 8.0, 16.0],
                    value=st.session_state.trip_speed_factor,
                    format_func=lambda v: f"{v:g}×",
                    key="trip_speed_select",
                    help="1× = real time. 4× is the demo default.",
                )
                if st.button("▶ Start journey", type="primary", use_container_width=True):
                    st.session_state.trip_speed_factor = float(speed)
                    src_route = plan.get(mode_pick) or plan["safest"]
                    o_label = "Your location"
                    new_trip = cp.start_trip(
                        src_route,
                        origin_label=o_label,
                        dest_label=plan.get("dest_label", "Destination"),
                        speed_factor=float(speed),
                    )
                    st.session_state.trip = new_trip
                    # Departure broadcast
                    if new_trip.alerts:
                        br = cp.dispatch_broadcasts(
                            new_trip.alerts[-1], new_trip,
                            st.session_state.contacts,
                            log_path=DATA / "notifications.csv",
                        )
                        st.session_state.trip_broadcasts.extend(br)
                    st.rerun()
            elif trip is not None and trip.status == "active":
                cba, cbb, cbc, cbd = st.columns(4)
                with cba:
                    if st.button("⏸ Pause", use_container_width=True, key="trip_pause"):
                        cp.pause_trip(trip); st.rerun()
                with cbb:
                    new_speed = st.select_slider(
                        "Speed",
                        options=[1.0, 2.0, 4.0, 8.0, 16.0],
                        value=trip.speed_factor,
                        format_func=lambda v: f"{v:g}×",
                        key="trip_speed_active",
                        label_visibility="collapsed",
                    )
                    if abs(new_speed - trip.speed_factor) > 1e-3:
                        trip.speed_factor = float(new_speed)
                        st.session_state.trip_speed_factor = float(new_speed)
                with cbc:
                    if st.button("🆘 Manual SOS", use_container_width=True, key="trip_manual_sos"):
                        a = cp.trigger_user_sos(trip)
                        br = cp.dispatch_broadcasts(
                            a, trip, st.session_state.contacts,
                            log_path=DATA / "notifications.csv",
                        )
                        st.session_state.trip_broadcasts.extend(br)
                        st.rerun()
                with cbd:
                    if st.button("✕ Cancel", use_container_width=True, key="trip_cancel"):
                        cp.cancel_trip(trip)
                        st.session_state.trip_log.append(cp.trip_digest(trip))
                        st.rerun()
            elif trip is not None and trip.status == "paused":
                cba, cbb = st.columns(2)
                with cba:
                    if st.button("▶ Resume", type="primary", use_container_width=True, key="trip_resume"):
                        cp.resume_trip(trip); st.rerun()
                with cbb:
                    if st.button("✕ Cancel", use_container_width=True, key="trip_cancel_p"):
                        cp.cancel_trip(trip)
                        st.session_state.trip_log.append(cp.trip_digest(trip))
                        st.rerun()
            elif trip is not None and trip.status in ("completed", "cancelled"):
                cba, cbb = st.columns(2)
                with cba:
                    if st.button("Plan another", type="primary", use_container_width=True, key="trip_replan"):
                        st.session_state.trip = None
                        st.session_state.trip_broadcasts = []
                        st.rerun()
                with cbb:
                    if st.button("Clear trip", use_container_width=True, key="trip_clear"):
                        st.session_state.trip = None
                        st.session_state.trip_broadcasts = []
                        st.rerun()

        with ctrl_r:
            if trip is not None and trip.status == "active":
                st.session_state.trip_auto_advance = st.toggle(
                    "Auto-advance (refresh every 2s)",
                    value=st.session_state.trip_auto_advance,
                    key="trip_auto_toggle",
                )
                pos = trip.position()
                if pos:
                    here_safety = compute_safety(
                        pos[0], pos[1],
                        incidents=inc_df.to_dict("records") if not inc_df.empty else [],
                        geofences=GEOFENCES,
                        pois=poi_df.to_dict("records") if not poi_df.empty else [],
                    )
                    band_c = band_color(here_safety.band)
                    st.markdown(
                        f"<div style='display:flex; gap:10px; align-items:center; margin-top:6px;'>"
                        f"<div style='width:10px; height:10px; border-radius:50%; background:{band_c}; box-shadow:0 0 10px {band_c};'></div>"
                        f"<div><div style='font-size:.62rem;letter-spacing:.14em;text-transform:uppercase;color:#8892A6;font-weight:700;'>"
                        f"Live spot safety</div>"
                        f"<div style='font-size:1.05rem; font-weight:800; color:{band_c};'>{here_safety.score} · {here_safety.band}</div></div>"
                        "</div>",
                        unsafe_allow_html=True,
                    )

        # ---- BODY: map + side panel ----
        if trip is not None:
            map_col, side_col = st.columns([3, 2], gap="large")

            with map_col:
                # Build map: route line + heartbeats trail + current pulsing dot
                accent = ROUTE_ACCENT.get(trip.plan.route_mode, "#5EEAD4")
                rgb = {
                    "safest":          [61, 169, 252],
                    "fastest":         [249, 196, 64],
                    "forecast-safest": [167, 139, 250],
                }.get(trip.plan.route_mode, [94, 234, 212])

                extras = _route_path_layer(
                    type("R", (), {"coords": trip.plan.coords, "mode": trip.plan.route_mode})(),
                    rgb, glow_width=10,
                )
                # Trail of past heartbeats
                if len(trip.heartbeats) >= 2:
                    trail = [[lon, lat] for _, lat, lon, _ in trip.heartbeats]
                    extras.append(pdk.Layer(
                        "PathLayer",
                        data=[{"path": trail}],
                        get_path="path",
                        get_color=[94, 234, 212, 200],
                        get_width=3, width_min_pixels=3, rounded=True,
                    ))
                # Current position — big pulsing dot
                pos = trip.position() or trip.plan.coords[0]
                extras.append(pdk.Layer(
                    "ScatterplotLayer",
                    data=pd.DataFrame([{"lat": pos[0], "lon": pos[1], "name": "you are here"}]),
                    get_position='[lon, lat]',
                    get_fill_color=[94, 234, 212, 230],
                    get_radius=70, pickable=True,
                    stroked=True, get_line_color=[14, 17, 23], line_width_min_pixels=2,
                ))
                extras.append(pdk.Layer(
                    "ScatterplotLayer",
                    data=pd.DataFrame([{"lat": pos[0], "lon": pos[1]}]),
                    get_position='[lon, lat]',
                    get_fill_color=[94, 234, 212, 60],
                    get_radius=180,
                ))
                # Origin & destination markers
                if trip.plan.coords:
                    extras.append(pdk.Layer(
                        "ScatterplotLayer",
                        data=pd.DataFrame([
                            {"lat": trip.plan.coords[0][0], "lon": trip.plan.coords[0][1], "name": "Start"},
                            {"lat": trip.plan.coords[-1][0], "lon": trip.plan.coords[-1][1], "name": trip.plan.dest_label},
                        ]),
                        get_position='[lon, lat]',
                        get_fill_color=[83, 227, 166],
                        get_radius=55, pickable=True,
                        stroked=True, get_line_color=[14, 17, 23], line_width_min_pixels=2,
                    ))

                view = pdk.ViewState(latitude=pos[0], longitude=pos[1], zoom=13)
                draw_map_layers(
                    inc_df, bcast_df, poi_df, my,
                    show_heatmap=True,
                    extra_layers=extras,
                    view_state_override=view,
                )
                legend = (
                    f"🟦/🟧/🟪 planned route · 🟢 trail (past {len(trip.heartbeats)}) · "
                    "🟡 current position · heatmap = recent incident risk"
                )
                st.caption(legend)

                # Look-ahead panel
                inc_rec = inc_df.to_dict("records") if not inc_df.empty else []
                poi_rec = poi_df.to_dict("records") if not poi_df.empty else []
                ahead = []
                # 3 evenly-spaced look-ahead slices: 0.4, 0.9, 1.5 km
                for dk in (0.4, 0.9, 1.5):
                    target_km = trip.km_travelled + dk
                    pt = cp._interp_position(trip.plan, target_km)
                    r = point_risk(pt[0], pt[1], inc_rec, GEOFENCES, poi_rec)
                    cat = cp._dominant_category_at(pt[0], pt[1], incidents=inc_rec)
                    haz = cat.title() if cat else ""
                    ahead.append((dk, r, haz))
                render_lookahead_panel(ahead)

            with side_col:
                st.markdown('<div class="ws-kicker">Alerts feed</div>', unsafe_allow_html=True)
                render_alert_feed(trip.alerts, datetime.utcnow(), limit=8)

                st.markdown(
                    '<div class="ws-kicker" style="margin-top:14px;">Trusted contacts</div>',
                    unsafe_allow_html=True,
                )
                render_contacts_strip(st.session_state.contacts)

                with st.expander("Manage contacts"):
                    cdf = pd.DataFrame([
                        {"name": c.name, "contact": c.contact, "relationship": c.relationship,
                         "opt_in": ", ".join(c.opt_in)}
                        for c in st.session_state.contacts
                    ]) if st.session_state.contacts else pd.DataFrame(
                        columns=["name", "contact", "relationship", "opt_in"]
                    )
                    edited = st.data_editor(
                        cdf, num_rows="dynamic", use_container_width=True,
                        column_config={
                            "opt_in": st.column_config.TextColumn(
                                help="Comma-separated: departure, arrival, auto_sos, risk_ahead, geofence_enter, info"
                            ),
                        },
                        key="contacts_editor",
                    )
                    if st.button("Save contacts", key="save_contacts_btn"):
                        new_contacts = []
                        for _, r in edited.iterrows():
                            name = str(r.get("name") or "").strip()
                            if not name:
                                continue
                            existing = next(
                                (c for c in st.session_state.contacts if c.name == name),
                                None,
                            )
                            cid = existing.id if existing else f"c-{uuid.uuid4().hex[:6]}"
                            opt_in = [s.strip() for s in str(r.get("opt_in", "")).split(",") if s.strip()] \
                                     or ["departure", "arrival", "auto_sos"]
                            new_contacts.append(cp.TrustedContact(
                                id=cid, name=name,
                                contact=str(r.get("contact") or ""),
                                relationship=str(r.get("relationship") or "friend"),
                                opt_in=opt_in,
                            ))
                        st.session_state.contacts = new_contacts
                        cp.save_contacts(new_contacts, DATA / "contacts.csv")
                        st.success(f"Saved {len(new_contacts)} contact(s).")

                st.markdown(
                    '<div class="ws-kicker" style="margin-top:14px;">Simulated dispatches</div>',
                    unsafe_allow_html=True,
                )
                render_broadcast_log(st.session_state.trip_broadcasts, datetime.utcnow(), limit=10)

            # Auto-advance loop — only when toggled on
            if trip.status == "active" and st.session_state.trip_auto_advance:
                _time.sleep(2.0)
                st.rerun()

    # ---------------- Forecast
    with tabs[4]:
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

    # ---------------- Sentinel (Day 26)
    with tabs[5]:
        st.subheader("🛰️ Sentinel — Live Cluster Intel")
        st.caption(
            "DBSCAN over haversine groups raw incidents into discrete hotspots; each "
            "cluster is then **graded by velocity** — recent rate vs its own historical "
            "baseline — so you see what's *escalating right now*, not just where activity "
            "has accumulated."
        )

        render_sentinel_pulse(sent_pulse)

        with st.expander("Sentinel parameters", expanded=False):
            cA, cB, cC, cD = st.columns(4)
            with cA:
                new_eps = st.number_input(
                    "Cluster radius ε (km)",
                    min_value=0.10, max_value=3.00, value=float(_sp["eps_km"]), step=0.05,
                    help="Two incidents within ε kilometres count as the same cluster (DBSCAN).",
                )
            with cB:
                new_min = st.number_input(
                    "Min samples", min_value=2, max_value=15,
                    value=int(_sp["min_samples"]), step=1,
                    help="Minimum incidents in an ε-ball to form a cluster core.",
                )
            with cC:
                new_recent = st.number_input(
                    "Recent window (days)", min_value=1, max_value=120,
                    value=int(_sp["recent_days"]), step=1,
                    help="Numerator of velocity — what counts as 'now'.",
                )
            with cD:
                new_baseline = st.number_input(
                    "Baseline window (days)", min_value=7, max_value=365,
                    value=int(_sp["baseline_days"]), step=1,
                    help="Denominator of velocity — the historical reference period that "
                         "ends where the recent window begins.",
                )
            if (new_eps, new_min, new_recent, new_baseline) != (
                _sp["eps_km"], _sp["min_samples"], _sp["recent_days"], _sp["baseline_days"]
            ):
                st.session_state.sentinel_params = {
                    "eps_km": float(new_eps),
                    "min_samples": int(new_min),
                    "recent_days": int(new_recent),
                    "baseline_days": int(new_baseline),
                }
                st.rerun()

        if not sent_clusters:
            render_sentinel_empty(
                hint=(
                    f"No clusters at ε={_sp['eps_km']:g} km · min-samples={_sp['min_samples']}. "
                    "Try loosening the parameters in the expander above."
                ),
            )
        else:
            # Cluster map: halo polygons + status-coloured centre markers + faint incident dots
            cluster_rows = [{
                "lat": c.center_lat, "lon": c.center_lon,
                "name": f"#{c.id+1} · {c.dominant_category}",
                "category": f"  ·  {c.status} · ×{c.velocity:.2f}",
                "radius_m": max(80, int(c.radius_km * 1000 * 0.6)),
            } for c in sent_clusters]
            cluster_df = pd.DataFrame(cluster_rows)

            extras = []
            for c in sent_clusters:
                hue = sn.STATUS_HUE.get(c.status, "#8892A6")
                h = hue.lstrip("#")
                r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
                ring = sn.cluster_polygon(c)
                extras.append(pdk.Layer(
                    "PolygonLayer",
                    data=[{"polygon": ring, "name": f"#{c.id+1} {c.dominant_category}",
                           "category": f"  ·  {c.status} · ×{c.velocity:.2f}"}],
                    get_polygon="polygon",
                    get_fill_color=[r, g, b, 40],
                    get_line_color=[r, g, b, 230],
                    line_width_min_pixels=2,
                    pickable=True,
                ))
            extras.append(pdk.Layer(
                "ScatterplotLayer",
                data=cluster_df,
                get_position='[lon, lat]',
                get_fill_color=[230, 233, 242, 220],
                get_line_color=[14, 17, 23],
                stroked=True,
                line_width_min_pixels=2,
                get_radius='radius_m',
                radius_min_pixels=8,
                pickable=True,
            ))

            # Re-centre on the cluster centroid for a clean overview
            mid_lat = sum(c.center_lat for c in sent_clusters) / len(sent_clusters)
            mid_lon = sum(c.center_lon for c in sent_clusters) / len(sent_clusters)
            view = pdk.ViewState(latitude=mid_lat, longitude=mid_lon, zoom=11.3)
            draw_map_layers(
                inc_df, bcast_df, poi_df, my,
                show_heatmap=False, extra_layers=extras, view_state_override=view,
            )
            st.caption(
                "🔴 critical · 🟠 emerging · 🟡 steady · 🟢 cooling — halo radius matches the "
                "cluster's geographic spread; centre dot size = recent count."
            )

            # Cluster cards
            render_sentinel_clusters(
                sent_clusters, my,
                recommended_action_fn=sn.recommended_action,
            )

            # Nearest-hotspot mini-callout (proximity intel for the user's location)
            nc = sn.nearest_cluster(sent_clusters, my["lat"], my["lon"])
            if nc:
                cl, d_edge = nc
                if d_edge == 0:
                    st.warning(
                        f"📍 Your current location is **inside** cluster #{cl.id+1} "
                        f"({cl.dominant_category}, {cl.status}, ×{cl.velocity:.2f} baseline)."
                    )
                else:
                    st.info(
                        f"📍 Nearest cluster: **#{cl.id+1} · {cl.dominant_category}** "
                        f"({cl.status}, ×{cl.velocity:.2f}) — **{d_edge:g} km** from its edge."
                    )

    # ---------------- Report Hazard
    with tabs[6]:
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
    with tabs[7]:
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
    with tabs[8]:
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

    # ---------------- Trip Log
    with tabs[9]:
        st.subheader("Trip Log")
        log = st.session_state.trip_log
        live = st.session_state.trip
        if live is not None and live.status == "active":
            st.caption("One trip is live — log appends on completion / cancellation.")
            from theme import render_trip_log_row as _ltlr  # noqa: F401
            digest = cp.trip_digest(live)
            digest["status"] = "active"
            render_trip_log_row(digest, datetime.utcnow())

        if not log:
            st.markdown(
                "<div style='color:#8892A6; font-size:.85rem;'>No completed trips yet. "
                "Plan a route, start a journey in the **Live Trip** tab, and the digest "
                "will land here when you arrive.</div>",
                unsafe_allow_html=True,
            )
        else:
            for d in reversed(log[-20:]):
                render_trip_log_row(d, datetime.utcnow())
            export = json.dumps(log, default=str, indent=2)
            st.download_button(
                "Export trip log (JSON)",
                data=export, file_name="waysafe_trips.json",
                mime="application/json",
            )

        # Existing PDF report — preserved for "trip + safety" docs
        st.markdown("---")
        st.markdown('<div class="ws-kicker">Generate PDF safety report</div>', unsafe_allow_html=True)
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import cm
        if st.button("Generate PDF"):
            buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=A4)
            w, h = A4; c.setFont("Helvetica-Bold", 14)
            c.drawString(2*cm, h-2*cm, "Trip & Safety Report (POC)")
            c.setFont("Helvetica", 10)
            c.drawString(2*cm, h-2.7*cm,
                         f"User: {st.session_state.user}  |  Generated: {datetime.utcnow().isoformat()}Z")
            y = h - 3.5*cm
            if log:
                c.setFont("Helvetica-Bold", 11); c.drawString(2*cm, y, "Recent trips"); y -= 0.6*cm
                c.setFont("Helvetica", 9)
                for d in list(reversed(log))[:8]:
                    c.drawString(2*cm, y,
                                 f"- {d.get('started_at','')[:16].replace('T',' ')} · "
                                 f"{d.get('origin','?')} → {d.get('destination','?')} · "
                                 f"{d.get('route_mode','—')} · {d.get('km_travelled', 0):g}/{d.get('distance_km', 0):g} km · "
                                 f"{d.get('status','')}")
                    y -= 0.6*cm
            inc_mine = inc_df[inc_df["user"] == st.session_state.user].tail(5)
            if not inc_mine.empty:
                c.setFont("Helvetica-Bold", 11); y -= 0.3*cm; c.drawString(2*cm, y, "Recent reports"); y -= 0.6*cm
                c.setFont("Helvetica", 9)
                for _, r in inc_mine.iterrows():
                    c.drawString(2*cm, y, f"- {r['created_at'][:19]}Z • {r['category']} @ ({r['lat']:.4f},{r['lon']:.4f}) • status={r['status']}")
                    y -= 0.6*cm
            c.showPage(); c.save(); buf.seek(0)
            b64 = base64.b64encode(buf.read()).decode()
            st.markdown(
                f'<a download="trip_report.pdf" href="data:application/pdf;base64,{b64}">Download Trip PDF</a>',
                unsafe_allow_html=True,
            )

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
