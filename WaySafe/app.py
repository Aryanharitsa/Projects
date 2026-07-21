
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
    render_advisory_brief, render_advisory_empty,
    render_compass, render_compass_empty,
    render_staysafe, render_staysafe_empty,
    render_refuge, render_refuge_empty,
    render_tempo, render_tempo_empty,
    render_echo, render_echo_empty,
    render_prism, render_prism_empty,
    render_odyssey, render_odyssey_empty,
)
import companion as cp
import itinerary as itn
import sentinel as sn
import advisory as adv
import compass as cmp
import stays as sts
import refuge as rfg
import tempo as tmp
import echo as ech
import prism as pr
import odyssey as ody
import nomad as nmd
import convoy as cvy

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
        "Pulse", "Beacon", "Map", "Plan Route", "Itinerary", "Live Trip", "Forecast",
        "Advisory", "Compass", "StaySafe", "Sentinel", "Refuge", "Tempo",
        "Report Hazard", "Alerts", "SOS", "Trip Log", "Echo", "Prism", "Odyssey",
        "Nomad", "Convoy",
    ]
    tabs = st.tabs(tab_labels)

    # ---------------- Pulse — Today's Outlook (Day 56)
    # The morning-brief surface — re-runs Safety, Forecast, Sentinel and Refuge
    # for each watched point at `now` and at `now − 24h` and surfaces the
    # deltas. Pure composition of existing engines; lives at tabs[0] because
    # this is what the traveller opens first thing in the morning.
    with tabs[0]:
        import pulse as pls

        st.subheader("Pulse — Today's Outlook")
        st.caption(
            "A one-page morning brief: every watched point re-scored at **now** "
            "and at **now − 24 h**, the joint forecast curve across all of them, "
            "Sentinel intersections, and a prioritised plan-of-day. "
            "Composes the rest of WaySafe — adds zero new physics."
        )

        # Default watched roster: the user's current location as "stay",
        # plus the two closest help-or-named POIs we can find (so the brief
        # always has at least one destination to talk about).
        if "pulse_watched" not in st.session_state:
            seed: list[dict] = [
                {"kind": "stay", "label": "Current location",
                 "lat": float(my["lat"]), "lon": float(my["lon"])},
            ]
            if not poi_df.empty:
                # Pick two non-help-POI named places near the user; fall back
                # to the first two rows if the radius search is empty.
                _picked = 0
                for _, r in poi_df.iterrows():
                    if _picked >= 2:
                        break
                    try:
                        d = haversine_km(my["lat"], my["lon"], float(r["lat"]), float(r["lon"]))
                    except Exception:
                        continue
                    if d > 5.0:
                        continue
                    if str(r.get("ptype", "")).lower() in {"hospital", "police", "clinic", "fire"}:
                        continue
                    seed.append({
                        "kind": "destination", "label": str(r["name"]),
                        "lat": float(r["lat"]), "lon": float(r["lon"]),
                    })
                    _picked += 1
            st.session_state.pulse_watched = seed

        with st.expander("Watched points", expanded=False):
            st.caption(
                "Edit the roster of points the brief is about. Mark exactly one "
                "as `stay` — the refuge-readiness tile checks that one."
            )
            edited = st.data_editor(
                pd.DataFrame(st.session_state.pulse_watched),
                key="pulse_watched_editor", use_container_width=True, num_rows="dynamic",
                column_config={
                    "kind": st.column_config.SelectboxColumn(
                        "kind", options=["stay", "destination", "custom"], width="small",
                    ),
                    "label": st.column_config.TextColumn("label", width="medium"),
                    "lat": st.column_config.NumberColumn("lat", format="%.5f"),
                    "lon": st.column_config.NumberColumn("lon", format="%.5f"),
                },
            )
            cols_e = st.columns([1, 1, 4])
            if cols_e[0].button("Save roster", key="pulse_save_roster"):
                st.session_state.pulse_watched = edited.to_dict("records")
                st.success(f"Saved {len(st.session_state.pulse_watched)} watched point(s).")
            if cols_e[1].button("Reset to defaults", key="pulse_reset_roster"):
                del st.session_state.pulse_watched
                st.rerun()

        if st.button("Compose Pulse", type="primary", use_container_width=True,
                     key="pulse_compose"):
            roster_rows = st.session_state.pulse_watched
            watched: list[pls.WatchedPoint] = []
            for r in roster_rows:
                try:
                    la = float(r["lat"]); lo = float(r["lon"])
                    if la != la or lo != lo:  # NaN
                        continue
                    watched.append(pls.WatchedPoint(
                        kind=str(r.get("kind", "destination")) or "destination",
                        label=str(r.get("label", "Point")) or "Point",
                        lat=la, lon=lo,
                    ))
                except Exception:
                    continue
            if not watched:
                st.warning("Add at least one watched point with a valid lat/lon.")
            else:
                with st.spinner("Re-scoring across every WaySafe engine…"):
                    forecaster = get_forecaster()
                    pulse_day = pls.compose_pulse(
                        watched=watched,
                        incidents=_inc_records, geofences=GEOFENCES,
                        pois=poi_df.to_dict("records") if not poi_df.empty else [],
                        forecaster=forecaster, now=datetime.utcnow(),
                        clusters=sent_clusters,
                    )
                st.session_state.pulse_day = pulse_day

        from theme import render_pulse, render_pulse_empty
        pd_day = st.session_state.get("pulse_day")
        if pd_day is None:
            render_pulse_empty()
        else:
            render_pulse(pd_day)

            with st.expander("Exports"):
                col_j, col_m = st.columns(2)
                col_j.download_button(
                    "Download JSON",
                    data=pd_day.to_json().encode("utf-8"),
                    file_name=f"pulse_{pd_day.now.strftime('%Y%m%d_%H%M')}.json",
                    mime="application/json",
                    use_container_width=True,
                )
                col_m.download_button(
                    "Download Markdown",
                    data=pd_day.to_markdown().encode("utf-8"),
                    file_name=f"pulse_{pd_day.now.strftime('%Y%m%d_%H%M')}.md",
                    mime="text/markdown",
                    use_container_width=True,
                )

    # ---------------- Beacon — Group Safety Coordinator (Day 61)
    # The first WaySafe surface that thinks in terms of a group instead of
    # a single point. Pure composition over `compute_safety` + `point_risk`
    # — zero new physics. Same composer family as Pulse / SynapseOS Pulse /
    # TITAN Pulse: every number comes from an engine that already shipped.
    with tabs[1]:
        import beacon as bcn

        st.subheader("Beacon — Group Safety Coordinator")
        st.caption(
            "Score your **group** as a whole, find the **meet-point** that "
            "minimises max-member walk-risk, and paint a **rendezvous corridor** "
            "from each member with per-waypoint risk samples. Built for "
            "families, student trips, business teams — 2–6 members."
        )

        # Default roster — the user's current location seeded as the lead +
        # three small perturbations so the demo always has a meaningful group
        # to render. Real users edit the roster in the data_editor below.
        if "beacon_roster" not in st.session_state:
            lat0, lon0 = float(my["lat"]), float(my["lon"])
            st.session_state.beacon_roster = [
                {"id": "m1", "label": "You (lead)",
                 "kind": "lead",      "lat": lat0,           "lon": lon0},
                {"id": "m2", "label": "Companion 1",
                 "kind": "traveller", "lat": lat0 + 0.0090,  "lon": lon0 - 0.0070},
                {"id": "m3", "label": "Companion 2",
                 "kind": "traveller", "lat": lat0 - 0.0075,  "lon": lon0 + 0.0095},
            ]

        with st.expander("Group roster", expanded=False):
            st.caption(
                "Edit the group — 2 to 6 members. `kind` weights the "
                "composite (minor / elder count for more safety weight)."
            )
            edited = st.data_editor(
                pd.DataFrame(st.session_state.beacon_roster),
                key="beacon_roster_editor",
                use_container_width=True, num_rows="dynamic",
                column_config={
                    "id": st.column_config.TextColumn("id", width="small"),
                    "kind": st.column_config.SelectboxColumn(
                        "kind",
                        options=["lead", "traveller", "minor", "elder", "guide"],
                        width="small",
                    ),
                    "label": st.column_config.TextColumn("label", width="medium"),
                    "lat": st.column_config.NumberColumn("lat", format="%.5f"),
                    "lon": st.column_config.NumberColumn("lon", format="%.5f"),
                },
            )
            cols_e = st.columns([1, 1, 1, 3])
            if cols_e[0].button("Save roster", key="beacon_save_roster"):
                st.session_state.beacon_roster = edited.to_dict("records")
                st.success(f"Saved {len(st.session_state.beacon_roster)} member(s).")
            if cols_e[1].button("Reset roster", key="beacon_reset_roster"):
                del st.session_state.beacon_roster
                st.rerun()
            if cols_e[2].button("Snap all to me", key="beacon_snap_roster",
                                help="Snap every member to your current location — "
                                     "useful when you've just regrouped."):
                lat0, lon0 = float(my["lat"]), float(my["lon"])
                for r in st.session_state.beacon_roster:
                    r["lat"] = lat0
                    r["lon"] = lon0
                st.rerun()

        if st.button("Compose Beacon", type="primary",
                     use_container_width=True, key="beacon_compose"):
            roster_rows = st.session_state.beacon_roster
            with st.spinner("Scoring members · ranking meet-points · drawing corridors…"):
                rep = bcn.compute_beacon(
                    roster_rows,
                    incidents=_inc_records, geofences=GEOFENCES,
                    pois=poi_df.to_dict("records") if not poi_df.empty else [],
                    now=datetime.utcnow(),
                )
            st.session_state.beacon_report = rep

        from theme import render_beacon, render_beacon_empty
        b_rep = st.session_state.get("beacon_report")
        if b_rep is None or not b_rep.members:
            render_beacon_empty()
        else:
            render_beacon(b_rep)

            # ---- Map of members + corridors + meet-points ----
            if b_rep.chosen is not None:
                st.markdown("##### Group map")
                # Members: scatter, band-colored.
                band_rgb = {
                    "Safe":      [83, 227, 166],
                    "Caution":   [249, 196, 64],
                    "High Risk": [255, 127, 80],
                    "Danger":    [255, 61, 96],
                    "Unknown":   [136, 146, 166],
                }
                member_records = [
                    {
                        "lat": float(s.member.lat),
                        "lon": float(s.member.lon),
                        "label": s.member.label,
                        "kind": s.member.kind,
                        "score": int(s.score),
                        "band": s.band,
                        "color": band_rgb.get(s.band, [136, 146, 166]),
                    }
                    for s in b_rep.members
                ]
                member_layer = pdk.Layer(
                    "ScatterplotLayer",
                    data=member_records,
                    get_position="[lon, lat]",
                    get_radius=90,
                    get_fill_color="color",
                    get_line_color=[255, 255, 255, 180],
                    line_width_min_pixels=2,
                    pickable=True,
                    radius_min_pixels=8,
                )
                # Meet-point: gold star.
                meet_records = [{
                    "lat": float(b_rep.chosen.lat),
                    "lon": float(b_rep.chosen.lon),
                    "label": b_rep.chosen.label,
                    "score": int(b_rep.chosen.score),
                }]
                meet_layer = pdk.Layer(
                    "ScatterplotLayer",
                    data=meet_records,
                    get_position="[lon, lat]",
                    get_radius=160,
                    get_fill_color=[249, 196, 64, 230],
                    get_line_color=[255, 255, 255, 230],
                    line_width_min_pixels=3,
                    pickable=True,
                    radius_min_pixels=12,
                )
                # Rendezvous corridors — one PathLayer per member, hue-graded
                # by peak risk.
                cor_records = []
                for cor in b_rep.corridors:
                    path = [[lo, la] for la, lo in cor.coords]
                    if cor.peak_risk >= 0.55:
                        color = [255, 61, 96, 200]
                    elif cor.peak_risk >= 0.35:
                        color = [249, 196, 64, 200]
                    else:
                        color = [61, 169, 252, 200]
                    cor_records.append({
                        "path": path,
                        "color": color,
                        "peak_risk": cor.peak_risk,
                        "member_id": cor.member_id,
                    })
                corridor_layer = pdk.Layer(
                    "PathLayer",
                    data=cor_records,
                    get_path="path",
                    get_color="color",
                    width_scale=4, width_min_pixels=3,
                    pickable=False,
                )
                # Auto-fit the view around all members + meet-point.
                all_lats = [r["lat"] for r in member_records] + [b_rep.chosen.lat]
                all_lons = [r["lon"] for r in member_records] + [b_rep.chosen.lon]
                view = pdk.ViewState(
                    latitude=sum(all_lats) / len(all_lats),
                    longitude=sum(all_lons) / len(all_lons),
                    zoom=14, pitch=0,
                )
                st.pydeck_chart(pdk.Deck(
                    layers=[corridor_layer, member_layer, meet_layer],
                    initial_view_state=view,
                    map_style=None,
                    tooltip={
                        "html": "<b>{label}</b><br/>score: {score}<br/>{band}",
                        "style": {"color": "#E6EAF2"},
                    },
                ), use_container_width=True)
                st.caption(
                    "● members coloured by band · ★ chosen meet-point in gold · "
                    "corridors painted blue / amber / rose by peak risk."
                )

            with st.expander("Exports"):
                col_j, col_m = st.columns(2)
                col_j.download_button(
                    "Download JSON",
                    data=b_rep.to_json().encode("utf-8"),
                    file_name=f"beacon_{b_rep.now.strftime('%Y%m%d_%H%M')}.json",
                    mime="application/json",
                    use_container_width=True,
                )
                col_m.download_button(
                    "Download Markdown",
                    data=b_rep.to_markdown().encode("utf-8"),
                    file_name=f"beacon_{b_rep.now.strftime('%Y%m%d_%H%M')}.md",
                    mime="text/markdown",
                    use_container_width=True,
                )

    # ---------------- Map
    with tabs[2]:
        render_sentinel_watch_banner(sent_pulse)
        draw_map_layers(inc_df, bcast_df, poi_df, my, show_heatmap=st.session_state.show_heatmap)
        st.caption("🔴 verified incident · 🟡 pending · 🟢 help POI · 🟠 risk zone · 🔵 active broadcast")

    # ---------------- Plan Route (long-overdue Day-6 wiring)
    with tabs[3]:
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
    with tabs[4]:
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
    with tabs[5]:
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
    with tabs[6]:
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

    # ---------------- Advisory (Day 31) — pre-trip safety brief
    with tabs[7]:
        st.subheader("🧭 Travel Advisory")
        st.caption(
            "A single-page safety brief that fuses **Safety Intelligence**, "
            "**Sentinel** cluster activity, **Forecast** depart windows, geofences, "
            "and nearest help — for any destination. Export it as JSON, copy as "
            "markdown, or print the polished **PDF brief** to carry offline."
        )

        target_modes = ["Your current location", "Pick a POI", "Custom lat/lon"]
        adv_mode = st.radio(
            "Target",
            target_modes,
            horizontal=True,
            label_visibility="collapsed",
            key="advisory_target_mode",
        )

        adv_label_default = "Your location"
        my2 = st.session_state.current_loc
        a_lat, a_lon = float(my2["lat"]), float(my2["lon"])
        adv_label = adv_label_default

        if adv_mode == "Pick a POI":
            poi_options = [f"{r['name']} · {r['ptype']}" for _, r in poi_df.iterrows()] if not poi_df.empty else []
            if poi_options:
                chosen = st.selectbox(
                    "Destination", poi_options, key="advisory_poi_select",
                )
                idx = poi_options.index(chosen)
                row = poi_df.iloc[idx]
                a_lat, a_lon = float(row["lat"]), float(row["lon"])
                adv_label = str(row["name"])
            else:
                st.info("No POIs in the dataset yet — switch to Custom lat/lon.")
        elif adv_mode == "Custom lat/lon":
            colL, colC, colR = st.columns([3, 2, 2])
            with colL:
                custom_name = st.text_input(
                    "Place name", value="Custom destination", key="advisory_custom_name",
                )
            with colC:
                a_lat = st.number_input(
                    "Lat", value=float(my2["lat"]), format="%.6f", key="advisory_custom_lat",
                )
            with colR:
                a_lon = st.number_input(
                    "Lon", value=float(my2["lon"]), format="%.6f", key="advisory_custom_lon",
                )
            adv_label = custom_name or f"({a_lat:.4f},{a_lon:.4f})"

        with st.expander("Brief settings", expanded=False):
            c1, c2 = st.columns(2)
            with c1:
                adv_radius = st.slider(
                    "Scan radius (km)", min_value=0.5, max_value=5.0, value=2.0, step=0.5,
                    key="advisory_radius",
                )
            with c2:
                adv_lookback = st.slider(
                    "Incident lookback (days)", min_value=3, max_value=30, value=7, step=1,
                    key="advisory_lookback",
                )

        brief = adv.build_brief(
            a_lat, a_lon, adv_label,
            inc_df=inc_df, poi_df=poi_df, geofences=GEOFENCES,
            forecaster=get_forecaster(),
            sentinel_clusters=sent_clusters,
            risk_pulse=sent_pulse,
            radius_km=float(adv_radius),
            lookback_days=int(adv_lookback),
        )

        render_advisory_brief(brief)

        st.markdown("---")
        cdl1, cdl2, cdl3 = st.columns(3)
        with cdl1:
            try:
                pdf_bytes = adv.brief_to_pdf(brief)
                st.download_button(
                    "⬇️ Download PDF brief",
                    data=pdf_bytes,
                    file_name=(
                        f"waysafe_advisory_{adv_label.replace(' ', '_').lower()}_"
                        f"{brief.generated_at:%Y%m%d_%H%M}.pdf"
                    ),
                    mime="application/pdf",
                    use_container_width=True,
                )
            except Exception as _e:
                st.error(f"PDF export failed: {_e}")
        with cdl2:
            st.download_button(
                "⬇️ Download JSON",
                data=json.dumps(adv.brief_to_json(brief), indent=2),
                file_name=(
                    f"waysafe_advisory_{adv_label.replace(' ', '_').lower()}_"
                    f"{brief.generated_at:%Y%m%d_%H%M}.json"
                ),
                mime="application/json",
                use_container_width=True,
            )
        with cdl3:
            md_text = adv.brief_to_markdown(brief)
            st.download_button(
                "⬇️ Download Markdown",
                data=md_text,
                file_name=(
                    f"waysafe_advisory_{adv_label.replace(' ', '_').lower()}_"
                    f"{brief.generated_at:%Y%m%d_%H%M}.md"
                ),
                mime="text/markdown",
                use_container_width=True,
            )

        with st.expander("View raw markdown / JSON"):
            t1, t2 = st.tabs(["Markdown", "JSON"])
            with t1:
                st.code(md_text, language="markdown")
            with t2:
                st.code(json.dumps(adv.brief_to_json(brief), indent=2), language="json")

    # ---------------- Compass — Destination Safety Showdown (Day 36)
    with tabs[8]:
        st.subheader("🧭 Compass — Destination Showdown")
        st.caption(
            "Can't decide *where* to go? Pick 2–5 candidates and Compass ranks "
            "them at your **depart time** — fusing the safety score, the "
            "depart-hour **forecast**, and live **Sentinel** cluster pressure into "
            "one verdict with a clear winner and a side-by-side factor matrix."
        )

        COMPASS_PRESETS = {
            "Baga": (15.5500, 73.7700),
            "Calangute": (15.5387, 73.7626),
            "Anjuna": (15.5850, 73.7440),
            "Candolim": (15.5180, 73.7620),
            "Vagator": (15.5990, 73.7440),
            "Panaji": (15.4966, 73.8262),
            "Old Goa": (15.5009, 73.9116),
            "Aguada Fort": (15.4925, 73.7825),
            "Ponda": (15.4020, 74.0080),
            "Margao": (15.2832, 73.9862),
        }

        csel1, csel2 = st.columns([3, 2])
        with csel1:
            chosen_presets = st.multiselect(
                "Destinations to compare",
                list(COMPASS_PRESETS.keys()),
                default=["Baga", "Anjuna", "Panaji"],
                key="compass_presets",
            )
        with csel2:
            include_me = st.checkbox("Include my current location", value=False, key="compass_include_me")
            compass_radius = st.slider(
                "Scan radius (km)", min_value=0.5, max_value=5.0, value=2.0, step=0.5,
                key="compass_radius",
            )

        with st.expander("Depart time"):
            now_dt = datetime.utcnow()
            dcol1, dcol2 = st.columns(2)
            with dcol1:
                depart_date = st.date_input("Date", value=now_dt.date(), key="compass_date")
            with dcol2:
                depart_time = st.time_input(
                    "Time", value=time(now_dt.hour, 0), step=1800, key="compass_time",
                )
            compass_depart = datetime.combine(depart_date, depart_time)
            st.caption(
                "The forecast term prices *when* you'd arrive — a calm spot at 3 PM "
                "is not the same spot at 2 AM."
            )

        with st.expander("Add a custom destination"):
            custom_dest_df = st.data_editor(
                pd.DataFrame(columns=["name", "lat", "lon"]),
                num_rows="dynamic",
                use_container_width=True,
                key="compass_custom_editor",
                column_config={
                    "name": st.column_config.TextColumn("Name"),
                    "lat": st.column_config.NumberColumn("Lat", format="%.5f"),
                    "lon": st.column_config.NumberColumn("Lon", format="%.5f"),
                },
            )

        # Assemble candidate targets: presets + my-location + custom rows.
        targets: list[tuple[float, float, str]] = []
        seen_labels: set[str] = set()
        if include_me:
            targets.append((float(my["lat"]), float(my["lon"]), "Your location"))
            seen_labels.add("your location")
        for name in chosen_presets:
            la, lo = COMPASS_PRESETS[name]
            targets.append((la, lo, name))
            seen_labels.add(name.lower())
        for _, r in custom_dest_df.iterrows():
            try:
                la, lo = float(r["lat"]), float(r["lon"])
            except (TypeError, ValueError):
                continue
            nm = str(r.get("name") or f"({la:.3f},{lo:.3f})").strip()
            if nm.lower() in seen_labels:
                continue
            targets.append((la, lo, nm))
            seen_labels.add(nm.lower())

        if len(targets) < 2:
            render_compass_empty()
        else:
            if len(targets) > 5:
                st.info(f"Comparing the first 5 of {len(targets)} destinations for readability.")
                targets = targets[:5]
            comparison = cmp.compare_destinations(
                targets,
                inc_df=inc_df, poi_df=poi_df, geofences=GEOFENCES,
                forecaster=get_forecaster(),
                sentinel_clusters=sent_clusters,
                now=datetime.utcnow(),
                depart=compass_depart,
                radius_km=float(compass_radius),
            )
            render_compass(comparison)

            with st.expander("Why each destination scored that way"):
                for v in comparison.destinations:
                    st.markdown(f"**{v.rank}. {v.label}** — compass {v.compass_score}/100 · {v.advisory_level}")
                    if v.safety_result and v.safety_result.factors:
                        for fct in v.safety_result.factors:
                            sign = "−" if fct["impact"] < 0 else "+"
                            st.caption(f"   {sign} {fct['label']} ({fct['impact']:+.0f})")
                    if v.best_hour_label:
                        st.caption(
                            f"   ↪ safer here at {v.best_hour_label} "
                            f"(forecast {int(round((v.best_hour_risk or 0) * 100))}%)"
                        )

            st.markdown("---")
            cmpc1, cmpc2 = st.columns(2)
            slug = "_vs_".join(v.label.replace(" ", "").lower() for v in comparison.destinations[:3])
            with cmpc1:
                st.download_button(
                    "⬇️ Download JSON",
                    data=json.dumps(cmp.comparison_to_json(comparison), indent=2),
                    file_name=f"waysafe_compass_{slug}_{comparison.generated_at:%Y%m%d_%H%M}.json",
                    mime="application/json",
                    use_container_width=True,
                )
            with cmpc2:
                st.download_button(
                    "⬇️ Download Markdown",
                    data=cmp.comparison_to_markdown(comparison),
                    file_name=f"waysafe_compass_{slug}_{comparison.generated_at:%Y%m%d_%H%M}.md",
                    mime="text/markdown",
                    use_container_width=True,
                )

    # ---------------- StaySafe — Accommodation Safety Picker (Day 41)
    with tabs[9]:
        st.subheader("🛏️ StaySafe — Accommodation Safety Picker")
        st.caption(
            "Compass compares places to *go*. StaySafe compares places to "
            "*sleep* — and the calculation is fundamentally different because "
            "you're physically at a stay for 16+ hours/day. Each candidate "
            "is scored across the **sleep**, **evening-return**, and "
            "**morning-depart** windows, plus walkability to help, quiet "
            "score, and reach to the area centre. Weights re-balance by "
            "traveller profile."
        )

        stays_csv_path = DATA / "stays.csv"
        try:
            preset_stays = sts.load_stays_csv(str(stays_csv_path))
        except FileNotFoundError:
            preset_stays = []
        preset_names = [s.name for s in preset_stays]

        scol1, scol2 = st.columns([3, 2])
        with scol1:
            chosen_stays = st.multiselect(
                "Candidate stays",
                preset_names,
                default=preset_names[:4] if len(preset_names) >= 4 else preset_names,
                key="staysafe_picked",
            )
        with scol2:
            profile = st.selectbox(
                "Traveller profile",
                list(sts.PROFILES.keys()),
                index=list(sts.PROFILES.keys()).index("Couple"),
                key="staysafe_profile",
                help="Re-balances the dimension weights for who's staying.",
            )
            nights = st.number_input(
                "Nights", min_value=1, max_value=21, value=2, step=1,
                key="staysafe_nights",
            )

        with st.expander("Check-in time"):
            now_dt = datetime.utcnow()
            chcol1, chcol2 = st.columns(2)
            with chcol1:
                ci_date = st.date_input("Date", value=now_dt.date(), key="staysafe_date")
            with chcol2:
                ci_time = st.time_input(
                    "Time", value=time(15, 0), step=1800, key="staysafe_time",
                )
            staysafe_checkin = datetime.combine(ci_date, ci_time)
            st.caption(
                "Used as the reference day for the forecast. The 24-hour "
                "sparkline on each card runs midnight → midnight of that day."
            )

        with st.expander("Add a custom stay (name + lat/lon)"):
            custom_stay_df = st.data_editor(
                pd.DataFrame(columns=["name", "lat", "lon", "kind"]),
                num_rows="dynamic",
                use_container_width=True,
                key="staysafe_custom_editor",
                column_config={
                    "name": st.column_config.TextColumn("Name"),
                    "lat": st.column_config.NumberColumn("Lat", format="%.5f"),
                    "lon": st.column_config.NumberColumn("Lon", format="%.5f"),
                    "kind": st.column_config.SelectboxColumn(
                        "Kind",
                        options=["hotel", "hostel", "homestay", "villa", "resort"],
                        default="hotel",
                    ),
                },
            )

        # Build candidate list: presets + custom rows. Dedupe by name.
        candidates: list[sts.StayCandidate] = []
        seen: set[str] = set()
        for s in preset_stays:
            if s.name in chosen_stays and s.name.lower() not in seen:
                candidates.append(s)
                seen.add(s.name.lower())
        for _, r in custom_stay_df.iterrows():
            try:
                la, lo = float(r["lat"]), float(r["lon"])
            except (TypeError, ValueError):
                continue
            nm = str(r.get("name") or f"({la:.3f},{lo:.3f})").strip()
            if not nm or nm.lower() in seen:
                continue
            candidates.append(sts.StayCandidate(
                name=nm, lat=la, lon=lo,
                kind=str(r.get("kind") or "hotel").strip() or "hotel",
            ))
            seen.add(nm.lower())

        if len(candidates) < 2:
            render_staysafe_empty(
                "Pick at least two stays above — try the 4 default picks and the "
                "podium will appear with a winner, margin, and a heat-mapped "
                "factor matrix."
            )
        else:
            if len(candidates) > 8:
                st.info(f"Comparing the first 8 of {len(candidates)} stays for readability.")
                candidates = candidates[:8]
            stay_result = sts.compare_stays(
                candidates,
                inc_df=inc_df, poi_df=poi_df, geofences=GEOFENCES,
                forecaster=get_forecaster(),
                sentinel_clusters=sent_clusters,
                check_in=staysafe_checkin,
                nights=int(nights),
                profile=profile,
            )
            render_staysafe(stay_result)

            with st.expander("Per-stay breakdown — windows + walk to help"):
                for v in stay_result.stays:
                    hosp = next((l for l in v.help_legs if l.category == "hospital"), None)
                    pol = next((l for l in v.help_legs if l.category == "police"), None)
                    hosp_s = f"{hosp.distance_km:.1f} km" if (hosp and hosp.distance_km is not None) else "—"
                    pol_s = f"{pol.distance_km:.1f} km" if (pol and pol.distance_km is not None) else "—"
                    st.markdown(
                        f"**{v.rank}. {v.candidate.name}** — "
                        f"stay-safe **{v.stay_score}/100** · {v.level}"
                    )
                    st.caption(
                        f"   sleep risk {int(round(v.sleep_risk_mean*100))}% · "
                        f"evening {int(round(v.evening_risk_mean*100))}% · "
                        f"morning {int(round(v.morning_risk_mean*100))}% · "
                        f"hospital {hosp_s} · police {pol_s} · "
                        f"clusters within 800m: {v.cluster_overlap}"
                        + (f" ({v.severe_cluster_count} severe)" if v.severe_cluster_count else "")
                    )
                    st.caption(f"   why: _{v.why_pick}_")

            st.markdown("---")
            sslug = "_vs_".join(
                v.candidate.name.replace(" ", "").lower()[:14]
                for v in stay_result.stays[:3]
            )
            sdl1, sdl2 = st.columns(2)
            with sdl1:
                st.download_button(
                    "⬇️ Download JSON",
                    data=json.dumps(sts.comparison_to_json(stay_result), indent=2),
                    file_name=f"waysafe_staysafe_{sslug}_{stay_result.generated_at:%Y%m%d_%H%M}.json",
                    mime="application/json",
                    use_container_width=True,
                )
            with sdl2:
                st.download_button(
                    "⬇️ Download Markdown",
                    data=sts.comparison_to_markdown(stay_result),
                    file_name=f"waysafe_staysafe_{sslug}_{stay_result.generated_at:%Y%m%d_%H%M}.md",
                    mime="text/markdown",
                    use_container_width=True,
                )

    # ---------------- Sentinel (Day 26)
    with tabs[10]:
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

    # ---------------- Refuge (Get Me to Safety)
    with tabs[11]:
        st.subheader("Refuge — Get Me to Safety")
        st.caption(
            "Ranks help POIs around you by a composite **Refuge Score** — "
            "proximity 35% · path safety 25% · trust tier 20% · open-now 15% · "
            "corridor crowd 5%. Not just the *nearest* help; the *best* refuge to reach right now."
        )

        rcol1, rcol2, rcol3 = st.columns([2, 1, 1])
        with rcol1:
            ref_radius = st.slider(
                "Scan radius (km)", min_value=1.0, max_value=8.0, value=4.0, step=0.5,
                key="refuge_radius",
                help="Refuges further than this are ignored. 4 km ≈ 50 min walk worst-case.",
            )
        with rcol2:
            ref_results = st.number_input(
                "Show top", min_value=1, max_value=8, value=5, step=1, key="refuge_max",
            )
        with rcol3:
            ref_now_override = st.checkbox(
                "Use current hour", value=True, key="refuge_use_now",
                help="Uncheck to test the 'after-dark' scoring with a custom hour.",
            )
            if not ref_now_override:
                ref_hour = st.slider("Hour (0-23)", 0, 23, 23, key="refuge_hour")

        ref_now = datetime.utcnow()
        if not ref_now_override:
            ref_now = ref_now.replace(hour=int(ref_hour), minute=0)

        scan = st.button(
            "🆘  Find Refuge Now", type="primary", use_container_width=True, key="refuge_scan",
        )

        if "refuge_result" not in st.session_state:
            st.session_state.refuge_result = None

        if scan:
            st.session_state.refuge_result = rfg.find_refuge(
                st.session_state.current_loc["lat"],
                st.session_state.current_loc["lon"],
                pois=poi_df,
                incidents=inc_df,
                geofences=geofences,
                now=ref_now,
                max_radius_km=float(ref_radius),
                max_results=int(ref_results),
                user=st.session_state.user,
            )

        result = st.session_state.refuge_result
        if result is None:
            render_refuge_empty()
        else:
            render_refuge(result)
            if result.options:
                top = result.options[0]
                col_a, col_b = st.columns(2)
                with col_a:
                    st.link_button(
                        f"🧭  Navigate to {top.poi_name}  ·  {top.distance_km*1000:.0f} m {top.bearing_label}",
                        top.nav_url, use_container_width=True,
                    )
                with col_b:
                    if st.button(
                        "📡  Activate Quiet Beacon",
                        use_container_width=True, key="refuge_beacon_btn",
                    ):
                        row = {
                            "id": str(uuid.uuid4()),
                            "incident_id": f"refuge-{uuid.uuid4().hex[:8]}",
                            "lat": result.here_lat,
                            "lon": result.here_lon,
                            "radius_km": round(top.distance_km, 3),
                            "created_at": result.now.isoformat(),
                        }
                        if st.session_state.offline:
                            st.session_state.outbox.append({"type": "broadcast", "row": row})
                            st.info("Beacon queued offline. Sync once you have signal.")
                        else:
                            try:
                                b = load_csv("broadcasts.csv")
                                b = pd.concat([b, pd.DataFrame([row])], ignore_index=True)
                                save_csv(b, "broadcasts.csv")
                                st.success(
                                    "Beacon active — trusted-contact ping logged. "
                                    "Stay on this screen while you walk."
                                )
                            except Exception as e:
                                st.warning(f"Beacon log failed locally: {e}")
                with st.expander("Why this ranking?"):
                    st.markdown(
                        "* **Proximity** is linear — 0 m → 1.0, scan-radius → 0.0.\n"
                        "* **Path safety** averages `1 − point_risk` across 5 evenly-spaced "
                        "waypoints between you and the refuge — that's the same `safety.point_risk` "
                        "the route planner uses, so Refuge agrees with the safest A* path.\n"
                        "* **Trust tier** is institutional weight — a police station is "
                        "intrinsically a stronger refuge than a 24/7 store even at the same distance.\n"
                        "* **Open now** degrades non-24/7 tiers (clinics, tourism desks) outside hours.\n"
                        "* **Corridor crowd** rewards routes whose midpoint sits near another POI — "
                        "a rough proxy for *populated, well-lit main road* vs *dark lane*.\n"
                    )

    # ---------------- Tempo (Departure-Window Optimizer)
    with tabs[12]:
        st.subheader("Tempo — Departure-Window Optimizer")
        st.caption(
            "*When* should you leave? Sweeps an arrival window × three route flavors "
            "(safest · balanced · fastest), runs the forecast-aware A* at every cell, and "
            "picks the minute that minimises **integrated risk along the actual corridor**. "
            "Compares the winner to *depart-now*, *earliest*, and *latest* baselines."
        )

        # ---- destination + dest_label
        tmp_poi_options = ["— custom lat/lon —"]
        if not poi_df.empty:
            tmp_poi_options += [f"{r['name']} · {r['ptype']}" for _, r in poi_df.iterrows()]
        tmp_dest_choice = st.selectbox(
            "Destination",
            tmp_poi_options,
            index=min(1, len(tmp_poi_options) - 1),
            key="tempo_dest_select",
        )
        if tmp_dest_choice == "— custom lat/lon —":
            tdc1, tdc2, tdc3 = st.columns([1, 1, 2])
            t_lat = tdc1.number_input(
                "Dest lat", value=15.5430, format="%.6f", key="tempo_dest_lat",
            )
            t_lon = tdc2.number_input(
                "Dest lon", value=73.7546, format="%.6f", key="tempo_dest_lon",
            )
            t_dest_label = tdc3.text_input("Label", value="destination", key="tempo_dest_label")
        else:
            t_row = poi_df.iloc[tmp_poi_options.index(tmp_dest_choice) - 1]
            t_lat = float(t_row["lat"]); t_lon = float(t_row["lon"])
            t_dest_label = str(t_row["name"])

        # ---- arrival window
        wc1, wc2, wc3, wc4 = st.columns([1, 1, 1, 1])
        with wc1:
            t_date = st.date_input(
                "Arrival date",
                value=datetime.utcnow().date(),
                key="tempo_arr_date",
            )
        with wc2:
            t_arr_start = st.time_input(
                "Earliest arrival",
                value=time(17, 0),
                key="tempo_arr_start",
            )
        with wc3:
            t_arr_end = st.time_input(
                "Latest arrival",
                value=time(19, 0),
                key="tempo_arr_end",
            )
        with wc4:
            t_step = st.selectbox(
                "Step (min)", [10, 15, 20, 30],
                index=0, key="tempo_step",
                help="Granularity of the arrival sweep. 10 min ≈ 13 slots over 2 h.",
            )

        # Flavor toggle
        fc1, fc2 = st.columns([2, 1])
        with fc1:
            tmp_flavors_choice = st.multiselect(
                "Route flavors",
                options=["safest", "balanced", "fastest"],
                default=["safest", "balanced", "fastest"],
                key="tempo_flavors",
                help=(
                    "safest = α=4.5 (max corridor avoidance); "
                    "balanced = α=2.5; fastest = α=0 (great-circle staircase)."
                ),
            )
        with fc2:
            tmp_use_now = st.checkbox(
                "Anchor 'now' to current time",
                value=True, key="tempo_anchor_now",
                help="Uncheck to plan a future trip without dimming past-depart cells.",
            )

        flavor_map = {"safest": 4.5, "balanced": 2.5, "fastest": 0.0}
        flavors = [(flavor_map[f], f) for f in tmp_flavors_choice] or [(4.5, "safest")]

        arr_start_dt = datetime.combine(t_date, t_arr_start)
        arr_end_dt = datetime.combine(t_date, t_arr_end)
        if arr_end_dt <= arr_start_dt:
            arr_end_dt = arr_start_dt + timedelta(hours=2)
        anchor_now = datetime.utcnow() if tmp_use_now else (arr_start_dt - timedelta(hours=12))

        # Quick window meta
        st.caption(
            f"Window: **{arr_start_dt.strftime('%a %H:%M')} → "
            f"{arr_end_dt.strftime('%H:%M')}** "
            f"({int((arr_end_dt - arr_start_dt).total_seconds() // 60)} min) "
            f"· {len(flavors)} flavor{'s' if len(flavors)!=1 else ''} · "
            f"step {t_step} min"
        )

        run_tempo = st.button(
            "⏱  Optimize Departure", type="primary",
            use_container_width=True, key="tempo_run",
        )

        if "tempo_result" not in st.session_state:
            st.session_state.tempo_result = None

        if run_tempo:
            with st.spinner("Sweeping arrival × flavor grid (A* per cell)…"):
                forecaster_t = get_forecaster()
                st.session_state.tempo_result = tmp.optimize_departure(
                    (my["lat"], my["lon"]),
                    (t_lat, t_lon),
                    forecaster=forecaster_t,
                    arrive_window=(arr_start_dt, arr_end_dt),
                    now=anchor_now,
                    incidents=inc_df.to_dict("records") if not inc_df.empty else [],
                    geofences=GEOFENCES,
                    pois=poi_df.to_dict("records") if not poi_df.empty else [],
                    step_min=int(t_step),
                    flavors=flavors,
                    dest_label=t_dest_label,
                )

        tempo_res = st.session_state.tempo_result
        if tempo_res is None:
            render_tempo_empty()
        else:
            render_tempo(tempo_res)

            # Winner corridor preview map
            if tempo_res.winner is not None and tempo_res.winner.coords:
                w = tempo_res.winner
                # Build runner-up overlays for context (faint).
                extras = []
                for c in tempo_res.runners_up:
                    if c.coords:
                        extras += _route_path_layer(c, [137, 146, 166], glow_width=5, line_width=2)
                extras += _route_path_layer(w, [83, 227, 166], glow_width=10, line_width=5)

                origin_pt = {"lat": my["lat"], "lon": my["lon"]}
                dest_pt = {"lat": w.coords[-1][0], "lon": w.coords[-1][1]}
                extras.append(pdk.Layer(
                    "ScatterplotLayer",
                    data=[origin_pt],
                    get_position=["lon", "lat"],
                    get_fill_color=[61, 169, 252, 220],
                    get_radius=80, radius_min_pixels=6,
                ))
                extras.append(pdk.Layer(
                    "ScatterplotLayer",
                    data=[dest_pt],
                    get_position=["lon", "lat"],
                    get_fill_color=[255, 106, 61, 220],
                    get_radius=80, radius_min_pixels=6,
                ))
                mid_lat = (my["lat"] + w.coords[-1][0]) / 2
                mid_lon = (my["lon"] + w.coords[-1][1]) / 2
                vs = pdk.ViewState(latitude=mid_lat, longitude=mid_lon, zoom=12)
                st.pydeck_chart(pdk.Deck(
                    layers=extras,
                    initial_view_state=vs,
                    map_style=None,
                    tooltip={"text": "winning corridor (green) · runners-up faint"},
                ))

            # Exports
            t1, t2 = st.columns(2)
            with t1:
                st.download_button(
                    "⬇ JSON (waysafe.tempo.v1)",
                    data=tempo_res.to_json().encode("utf-8"),
                    file_name=f"tempo_{tempo_res.winner.depart.strftime('%Y%m%dT%H%M') if tempo_res.winner else 'empty'}.json",
                    mime="application/json",
                    use_container_width=True,
                    key="tempo_dl_json",
                )
            with t2:
                st.download_button(
                    "⬇ Markdown digest",
                    data=tempo_res.to_markdown().encode("utf-8"),
                    file_name=f"tempo_{tempo_res.winner.depart.strftime('%Y%m%dT%H%M') if tempo_res.winner else 'empty'}.md",
                    mime="text/markdown",
                    use_container_width=True,
                    key="tempo_dl_md",
                )

            with st.expander("How Tempo scores a cell"):
                st.markdown(
                    "* **Probe** each flavor once at the window midpoint to learn its ETA.\n"
                    "* For each arrival slot `t_arr` and flavor `α`:\n"
                    "  `depart = t_arr − eta_α`; "
                    "run `plan_forecast_route(..., depart, α)`; "
                    "`risk_km = mean(forecast_blended_risk along corridor) × distance_km`.\n"
                    "* **Composite** = `100 × exp(−κ × risk_km)` with `κ = 0.35` "
                    "(risk_km 0.64→80 · 1.23→65 · 1.98→50 · 3.0→35).\n"
                    "* **Bands** mirror the rest of WaySafe: All-clear ≥80 · Caution 65 · "
                    "Elevated 50 · High Risk 35 · Danger < 35.\n"
                    "* **Winner** = highest composite among **feasible** cells "
                    "(depart ≥ now). Ties broken by lower risk-km, then higher min-safety, "
                    "then shorter ETA. Runners-up = next-best two within 6 pts.\n"
                    "* **Baselines**: depart-now (closest depart to `now`), earliest, latest. "
                    "Each comparison reports `Δcomposite` and `Δrisk-km` vs winner.\n"
                    "* `risk_samples` and `point_risk` are the *same* engine the "
                    "Plan-Route surface uses — Tempo's verdict always agrees with the "
                    "safest A* corridor at that depart-time.\n"
                )

    # ---------------- Report Hazard
    with tabs[13]:
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
    with tabs[14]:
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
    with tabs[15]:
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
    with tabs[16]:
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

    # ---------------- Echo — Post-Trip Debrief (Day 66)
    # The retrospective lens that completes the temporal loop. Pulse opens
    # the day (forward-looking), Tempo picks when to leave, Live Trip
    # streams alerts during, Echo debriefs the trip after. Pure
    # composition over the existing physics — see `echo.py` for the
    # composite formula and counterfactual recipe.
    with tabs[17]:
        st.subheader("Echo — Post-Trip Debrief")
        st.caption(
            "The *retrospective* lens. Pulse opens the day, Tempo picks the "
            "depart-minute, Live Trip streams alerts during. Echo composes the "
            "verdict after — composite trip score, counterfactual flavors at "
            "the same depart, calibration of the alert system against the "
            "trace, and a checklist of lessons. Pure composition over the "
            "existing physics; zero new physics."
        )

        live_trip = st.session_state.get("trip")
        echo_subject = None
        subject_label = ""
        if live_trip is not None:
            echo_subject = live_trip
            subject_label = (
                f"current trip · {live_trip.plan.origin_label} → "
                f"{live_trip.plan.dest_label} · status {live_trip.status}"
            )

        # Demo-trip launcher — synthesizes a quick Aguada → Baga journey at the
        # current depart-time so the surface has *something* to debrief on a
        # fresh app load (no need to run the Live Trip flow first).
        col_demo_l, col_demo_r = st.columns([3, 2])
        with col_demo_l:
            if echo_subject is None:
                st.markdown(
                    "<small style='color:#8892A6;'>No active trip in session. "
                    "Run a journey in the <b>Live Trip</b> tab, or click "
                    "<b>Run seeded demo trip</b> to debrief a canonical "
                    "Aguada → Baga route at the current time.</small>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"<small style='color:#8892A6;'>Debriefing the "
                    f"<b>{subject_label}</b>. Refresh after the trip completes "
                    f"for the full verdict.</small>",
                    unsafe_allow_html=True,
                )
        with col_demo_r:
            if st.button(
                "Run seeded demo trip",
                use_container_width=True,
                key="echo_demo_run",
                help=(
                    "Plans a safest route Aguada cliffs → Baga at Sat 22:00 "
                    "and simulates it to completion so Echo can debrief it."
                ),
            ):
                inc_rec = inc_df.to_dict("records") if not inc_df.empty else []
                poi_rec = poi_df.to_dict("records") if not poi_df.empty else []
                demo_depart = datetime(2026, 6, 27, 22, 0)
                demo_origin = (15.4925, 73.7825)
                demo_dest = (15.5550, 73.7700)
                demo_route = plan_safest_route(
                    demo_origin, demo_dest,
                    inc_rec, GEOFENCES, poi_rec, now=demo_depart,
                )
                demo_trip = cp.start_trip(
                    demo_route,
                    origin_label="Aguada cliffs",
                    dest_label="Baga",
                    now=demo_depart,
                )
                _now = demo_depart
                _steps = 0
                while demo_trip.status == "active" and _steps < 1000:
                    _now = _now + timedelta(seconds=30)
                    cp.tick(
                        demo_trip,
                        incidents=inc_rec, geofences=GEOFENCES, pois=poi_rec,
                        now=_now,
                    )
                    _steps += 1
                st.session_state["echo_demo_trip"] = demo_trip
                st.session_state["echo_demo_broadcasts"] = (
                    1 + (3 if demo_trip.auto_sos_fired else 0)
                )
                st.rerun()

        # Pick the subject: live trip wins; demo trip is the fallback.
        demo_trip = st.session_state.get("echo_demo_trip")
        if echo_subject is None and demo_trip is not None:
            echo_subject = demo_trip

        if echo_subject is None:
            render_echo_empty()
        else:
            inc_rec = inc_df.to_dict("records") if not inc_df.empty else []
            poi_rec = poi_df.to_dict("records") if not poi_df.empty else []
            try:
                forecaster_for_echo = get_forecaster()
            except Exception:
                forecaster_for_echo = None
            broadcasts_n = (
                len(st.session_state.get("trip_broadcasts", []))
                if echo_subject is live_trip
                else int(st.session_state.get("echo_demo_broadcasts", 0))
            )
            report = ech.compute_echo(
                echo_subject,
                incidents=inc_rec,
                geofences=GEOFENCES,
                pois=poi_rec,
                forecaster=forecaster_for_echo,
                broadcasts_count=broadcasts_n,
                now=datetime.utcnow(),
            )
            render_echo(report)

            st.markdown("---")
            colj, colm = st.columns(2)
            with colj:
                st.download_button(
                    "Download JSON (waysafe.echo.v1)",
                    data=report.to_json(),
                    file_name=f"waysafe_echo_{report.trip_id[:8]}.json",
                    mime="application/json",
                    use_container_width=True,
                )
            with colm:
                st.download_button(
                    "Download Markdown debrief",
                    data=report.to_markdown(),
                    file_name=f"waysafe_echo_{report.trip_id[:8]}.md",
                    mime="text/markdown",
                    use_container_width=True,
                )
            t_md, t_json = st.tabs(["Markdown preview", "JSON preview"])
            with t_md:
                st.markdown(report.to_markdown())
            with t_json:
                st.code(report.to_json(indent=2), language="json")

            if demo_trip is not None and echo_subject is demo_trip:
                if st.button("Clear demo trip", key="echo_demo_clear"):
                    st.session_state.pop("echo_demo_trip", None)
                    st.session_state.pop("echo_demo_broadcasts", None)
                    st.rerun()

    # ---------------- Prism — Persona-Aware Risk Lens (Day 71)
    # Re-prices every watched point under a chosen traveller persona.  Zero
    # new physics — the lens rescales the same factor ledger `safety.py`
    # already emits (geofence / incidents / late-night / help-POI), then
    # adds two persona-only extras (remote-help penalty, off-hour penalty).
    with tabs[18]:
        st.subheader("Prism — Persona-Aware Risk Lens")
        st.caption(
            "Every prior WaySafe surface scores the corridor for the *average* "
            "traveller. Prism re-prices it for **who's actually walking it** — "
            "solo woman, family with kids, senior, business, adventure, or "
            "backpacker group. Same physics, six lenses. Zero new measurements."
        )

        # Persona-picker strip.  Uses a horizontal radio so the row is a
        # single Streamlit widget (avoids the button-race that a chip grid
        # would introduce on re-run).
        persona_ids = list(pr.PERSONAS.keys())
        persona_labels = [
            f"{pr.PERSONAS[pid].icon}  {pr.PERSONAS[pid].label}"
            for pid in persona_ids
        ]
        if "prism_persona_id" not in st.session_state:
            st.session_state.prism_persona_id = pr.DEFAULT_PERSONA
        default_idx = persona_ids.index(st.session_state.prism_persona_id)
        picked_label = st.radio(
            "Traveller persona",
            persona_labels,
            index=default_idx,
            horizontal=True,
            key="prism_persona_radio",
            help=(
                "Rescales the base safety score under the selected persona. "
                "Nothing new is measured — the same geofence / incident / "
                "help-POI ledger is re-weighted."
            ),
        )
        selected_pid = persona_ids[persona_labels.index(picked_label)]
        st.session_state.prism_persona_id = selected_pid
        persona = pr.PERSONAS[selected_pid]

        # Watched-point roster.  Default = current location + top 3 named
        # POIs within 6 km of the user.  Persist so the analyst can pick
        # once and re-tune the persona to see the deltas.
        if "prism_watched" not in st.session_state:
            seed: list[dict] = [
                {"kind": "stay", "label": "Current location",
                 "lat": float(my["lat"]), "lon": float(my["lon"])},
            ]
            if not poi_df.empty:
                picked = 0
                for _, row in poi_df.iterrows():
                    if picked >= 3:
                        break
                    name = str(row.get("name") or "").strip()
                    if not name:
                        continue
                    try:
                        plat = float(row["lat"]); plon = float(row["lon"])
                    except Exception:
                        continue
                    if haversine_km(float(my["lat"]), float(my["lon"]), plat, plon) > 6.0:
                        continue
                    seed.append({"kind": "poi", "label": name, "lat": plat, "lon": plon})
                    picked += 1
            st.session_state.prism_watched = seed

        # UI for adding a custom point + reset button.
        with st.expander("Watched points", expanded=False):
            st.caption(
                "The roster Prism scores under the selected persona. Add "
                "any lat/lon; reset to defaults if the list drifts."
            )
            for i, w in enumerate(st.session_state.prism_watched):
                cols = st.columns([4, 2, 2, 1])
                cols[0].markdown(f"**{w['label']}**")
                cols[1].markdown(f"`{float(w['lat']):.4f}`")
                cols[2].markdown(f"`{float(w['lon']):.4f}`")
                if cols[3].button("Remove", key=f"prism_rm_{i}"):
                    st.session_state.prism_watched.pop(i)
                    st.rerun()
            with st.form(key="prism_add_form", clear_on_submit=True):
                a, b, c = st.columns([3, 2, 2])
                new_label = a.text_input("Label", value="", placeholder="e.g. Baga Beach")
                new_lat = b.number_input("Lat", value=float(my["lat"]),
                                         format="%.5f", key="prism_new_lat")
                new_lon = c.number_input("Lon", value=float(my["lon"]),
                                         format="%.5f", key="prism_new_lon")
                if st.form_submit_button("Add point"):
                    label = new_label.strip() or f"({new_lat:.3f}, {new_lon:.3f})"
                    st.session_state.prism_watched.append({
                        "kind": "custom", "label": label,
                        "lat": float(new_lat), "lon": float(new_lon),
                    })
                    st.rerun()
            if st.button("Reset to defaults", key="prism_reset"):
                st.session_state.pop("prism_watched", None)
                st.rerun()

        watched = st.session_state.get("prism_watched", [])
        if not watched:
            render_prism_empty(
                "No watched points on the roster. Open the expander above "
                "and add at least one lat/lon (your stay + a destination is "
                "a good starting pair)."
            )
        else:
            inc_rec = inc_df.to_dict("records") if not inc_df.empty else []
            poi_rec = poi_df.to_dict("records") if not poi_df.empty else []
            now = datetime.utcnow()
            report = pr.compute_prism_report(
                watched, persona, inc_rec, GEOFENCES, poi_rec, now=now,
            )

            show_matrix = st.toggle(
                "Show cross-persona matrix",
                value=True,
                key="prism_show_matrix",
                help=(
                    "Score every watched point under EVERY persona side by "
                    "side. Answers 'who does this corridor work for?'"
                ),
            )
            matrix = None
            if show_matrix:
                matrix = pr.compute_persona_matrix(
                    watched, inc_rec, GEOFENCES, poi_rec, now=now,
                )
            render_prism(report, matrix=matrix)

            st.markdown("---")
            colj, colm = st.columns(2)
            with colj:
                st.download_button(
                    "Download JSON (waysafe.prism.v1)",
                    data=report.to_json(),
                    file_name=f"waysafe_prism_{persona.id}.json",
                    mime="application/json",
                    use_container_width=True,
                )
            with colm:
                st.download_button(
                    "Download Markdown brief",
                    data=report.to_markdown(),
                    file_name=f"waysafe_prism_{persona.id}.md",
                    mime="text/markdown",
                    use_container_width=True,
                )
            t_md, t_json = st.tabs(["Markdown preview", "JSON preview"])
            with t_md:
                st.markdown(report.to_markdown())
            with t_json:
                st.code(report.to_json(indent=2), language="json")

    # ---------------- Odyssey — Multi-Day Trip Composer (Day 76)
    # The first WaySafe surface that scores an entire *multi-day* trip as
    # one deterministic report.  Composes every prior engine (safety,
    # forecast, routing corridor-sampling) over an ordered list of days,
    # each with a stay + 1..N stops + depart hour, and returns a
    # worst-day-weighted trip verdict plus a weakest-link callout with
    # ranked concrete swaps.
    with tabs[19]:
        st.subheader("Odyssey — Multi-Day Trip Composer")
        st.caption(
            "Every prior WaySafe surface is *single-day*.  Odyssey composes "
            "every engine — Safety, Forecast, corridor sampling — across a "
            "multi-day trip and returns one deterministic verdict, a "
            "**worst-day-weighted** trip score, a drift index, and a "
            "**weakest-link** callout with ranked one-tap swaps.  Zero new "
            "physics — the same ledger `Safety` prints."
        )

        # -- Day roster (session-persisted) --------------------------------
        if "ody_days" not in st.session_state:
            seed_pois = poi_df.to_dict("records") if not poi_df.empty else []
            seed = ody.default_seed_trip(
                home_lat=float(my["lat"]), home_lon=float(my["lon"]),
                pois=seed_pois, n_days=4,
            )
            # Convert dataclasses to editable dicts for st.data_editor.
            st.session_state.ody_days = [
                {
                    "date": d.date, "label": d.label,
                    "stay_label": d.stay_label,
                    "stay_lat": d.stay_lat, "stay_lon": d.stay_lon,
                    "depart_hour": d.depart_hour,
                    "transit_mode": d.transit_mode,
                    "stops": [
                        {"label": s.label, "lat": s.lat, "lon": s.lon,
                         "dwell_min": s.dwell_min}
                        for s in d.stops
                    ],
                }
                for d in seed
            ]

        c_top1, c_top2, c_top3 = st.columns([2, 1, 1])
        with c_top1:
            st.markdown(
                f"**Roster** — {len(st.session_state.ody_days)} day(s) · "
                f"add / remove / edit below.  Composition weights: "
                f"`{ody.STAY_WEIGHT}` stay + `{ody.STOPS_WEIGHT}` stops "
                f"+ `{ody.CORRIDOR_WEIGHT}` corridor · "
                f"trip = `{ody.MEAN_DAY_WEIGHT}` mean + "
                f"`{ody.MIN_DAY_WEIGHT}` min-day.",
            )
        with c_top2:
            if st.button("Reset roster", key="ody_reset",
                          help="Rebuild the seed trip from current location + nearest POIs."):
                st.session_state.pop("ody_days", None)
                st.rerun()
        with c_top3:
            if st.button("Add day", key="ody_add_day",
                          help="Append a blank day pinned to current location."):
                from datetime import timedelta as _tdlt
                last_date = (
                    st.session_state.ody_days[-1]["date"]
                    if st.session_state.ody_days else datetime.utcnow().date().isoformat()
                )
                try:
                    from datetime import date as _dt
                    next_date = (_dt.fromisoformat(last_date) + _tdlt(days=1)).isoformat()
                except ValueError:
                    next_date = datetime.utcnow().date().isoformat()
                st.session_state.ody_days.append({
                    "date": next_date,
                    "label": f"Day {len(st.session_state.ody_days)+1}",
                    "stay_label": "Base stay",
                    "stay_lat": float(my["lat"]),
                    "stay_lon": float(my["lon"]),
                    "depart_hour": 9, "transit_mode": "auto",
                    "stops": [],
                })
                st.rerun()

        # --- Per-day editor (expanders) ----------------------------------
        for i, day in enumerate(st.session_state.ody_days):
            with st.expander(
                f"Day {i+1} · {day.get('date','?')} · {day.get('label','?')} · "
                f"{len(day.get('stops',[]))} stop(s)",
                expanded=(i == 0),
            ):
                r1c1, r1c2, r1c3 = st.columns([2, 1, 1])
                day["label"] = r1c1.text_input(
                    "Day label", value=day.get("label",""), key=f"ody_label_{i}",
                )
                day["date"] = r1c2.text_input(
                    "Date (YYYY-MM-DD)", value=day.get("date",""), key=f"ody_date_{i}",
                )
                day["depart_hour"] = int(r1c3.number_input(
                    "Depart hour (0-23)", value=int(day.get("depart_hour", 9)),
                    min_value=0, max_value=23, step=1, key=f"ody_depart_{i}",
                ))

                r2c1, r2c2, r2c3, r2c4 = st.columns([2, 1, 1, 1])
                day["stay_label"] = r2c1.text_input(
                    "Stay label", value=day.get("stay_label",""), key=f"ody_stay_label_{i}",
                )
                day["stay_lat"] = float(r2c2.number_input(
                    "Stay lat", value=float(day.get("stay_lat", my["lat"])),
                    format="%.5f", key=f"ody_stay_lat_{i}",
                ))
                day["stay_lon"] = float(r2c3.number_input(
                    "Stay lon", value=float(day.get("stay_lon", my["lon"])),
                    format="%.5f", key=f"ody_stay_lon_{i}",
                ))
                day["transit_mode"] = r2c4.selectbox(
                    "Mode", options=["auto", "walk", "cab"],
                    index=["auto","walk","cab"].index(day.get("transit_mode","auto"))
                        if day.get("transit_mode","auto") in ("auto","walk","cab") else 0,
                    key=f"ody_mode_{i}",
                )

                # Stops sub-editor via data_editor for compactness.
                stops_df = pd.DataFrame(
                    day.get("stops", []) or [],
                    columns=["label", "lat", "lon", "dwell_min"],
                )
                if stops_df.empty:
                    stops_df = pd.DataFrame([
                        {"label": "", "lat": float(my["lat"]),
                         "lon": float(my["lon"]), "dwell_min": 60}
                    ]).iloc[0:0]
                edited = st.data_editor(
                    stops_df, key=f"ody_stops_{i}",
                    num_rows="dynamic", use_container_width=True,
                    column_config={
                        "label": st.column_config.TextColumn(
                            "Stop", help="Descriptive name of the stop"),
                        "lat": st.column_config.NumberColumn(
                            "Lat", format="%.5f"),
                        "lon": st.column_config.NumberColumn(
                            "Lon", format="%.5f"),
                        "dwell_min": st.column_config.NumberColumn(
                            "Dwell (min)", min_value=15, max_value=480, step=15),
                    },
                )
                stops_records = []
                for _, r in edited.iterrows():
                    try:
                        lab = str(r.get("label", "")).strip()
                        if not lab:
                            continue
                        stops_records.append({
                            "label": lab,
                            "lat": float(r.get("lat")),
                            "lon": float(r.get("lon")),
                            "dwell_min": int(r.get("dwell_min") or 60),
                        })
                    except (TypeError, ValueError):
                        continue
                day["stops"] = stops_records

                rm_c1, rm_c2 = st.columns([1, 4])
                if rm_c1.button("Remove day", key=f"ody_rm_{i}"):
                    st.session_state.ody_days.pop(i)
                    st.rerun()

        # --- Compose button ---------------------------------------------
        st.markdown("")
        c_run1, c_run2 = st.columns([1, 3])
        run_it = c_run1.button(
            "Compose Odyssey",
            key="ody_run",
            type="primary",
            use_container_width=True,
            help="Score every day, thread the aggregate, surface the weakest link.",
        )
        c_run2.caption(
            "Same inputs → same bytes. Runs in < 100 ms for a 7-day trip on a laptop."
        )

        # --- Convert roster → OdysseyDay list ---------------------------
        def _roster_to_days() -> list:
            out = []
            for d in st.session_state.ody_days:
                stops = tuple(
                    ody.Stop(
                        label=str(s.get("label","")),
                        lat=float(s.get("lat", 0.0)),
                        lon=float(s.get("lon", 0.0)),
                        dwell_min=int(s.get("dwell_min", 60)),
                    )
                    for s in d.get("stops", [])
                )
                try:
                    out.append(ody.OdysseyDay(
                        date=str(d.get("date","")),
                        label=str(d.get("label","")),
                        stay_lat=float(d.get("stay_lat", my["lat"])),
                        stay_lon=float(d.get("stay_lon", my["lon"])),
                        stay_label=str(d.get("stay_label","")),
                        stops=stops,
                        depart_hour=int(d.get("depart_hour", 9)),
                        transit_mode=str(d.get("transit_mode","auto")),
                    ))
                except (TypeError, ValueError):
                    continue
            return out

        if run_it or "ody_last_trip" not in st.session_state:
            days_in = _roster_to_days()
            if days_in:
                # Forecaster is optional — only build it if the app already
                # has one warm (avoids paying build cost on this tab).
                forecaster_local = None
                try:
                    forecaster_local = get_forecaster()
                except Exception:
                    forecaster_local = None
                trip = ody.compose_odyssey(
                    days=days_in,
                    incidents=inc_df.to_dict("records") if not inc_df.empty else [],
                    geofences=GEOFENCES,
                    pois=poi_df.to_dict("records") if not poi_df.empty else [],
                    forecaster=forecaster_local,
                )
                st.session_state.ody_last_trip = trip
            else:
                st.session_state.ody_last_trip = None

        trip = st.session_state.get("ody_last_trip")
        if trip is None or trip.n_days == 0:
            render_odyssey_empty(
                "Add at least one day above and press <b>Compose Odyssey</b>."
            )
        else:
            render_odyssey(trip)

            st.markdown("---")
            colj, colm = st.columns(2)
            with colj:
                st.download_button(
                    "Download JSON (waysafe.odyssey.v1)",
                    data=ody.to_json(trip),
                    file_name="waysafe_odyssey.json",
                    mime="application/json",
                    use_container_width=True,
                )
            with colm:
                st.download_button(
                    "Download Markdown brief",
                    data=ody.to_markdown(trip),
                    file_name="waysafe_odyssey.md",
                    mime="text/markdown",
                    use_container_width=True,
                )
            t_md, t_json = st.tabs(["Markdown preview", "JSON preview"])
            with t_md:
                st.markdown(ody.to_markdown(trip))
            with t_json:
                st.code(ody.to_json(trip, indent=2), language="json")

    # ---------------- Nomad — Adaptive Live Trip Reflow (Day 81)
    # Odyssey commits a multi-day trip at plan time. Nomad reflows what's
    # left of that trip after live signals have moved: fresh incidents on
    # tomorrow's corridor, a Sentinel cluster escalation, a widened
    # geofence. Zero new physics — the same day-composition engine
    # Odyssey uses is run against current signals for every upcoming day,
    # then seven concrete reflow strategies (TIME_SHIFT, STOP_DROP,
    # STOP_SUB, REST_DAY, SHORTEN, STAY_MOVE + STAY_COURSE baseline) are
    # simulated end-to-end and ranked by projected trip uplift.
    with tabs[20]:
        st.subheader("Nomad — Adaptive Live Trip Reflow")
        st.caption(
            "Odyssey commits the trip.  Nomad reflows what's *left* of it "
            "once live signals have moved.  Every upcoming day is "
            "re-composed under current incidents / geofences / POIs and "
            "seven concrete reflow strategies are simulated end-to-end, "
            "each ranked by projected trip-score uplift over "
            "**STAY_COURSE**.  Same physics as Odyssey — zero new "
            "measurements, deterministic to the byte."
        )

        # Nomad needs an existing Odyssey TripReport to reflow. If the
        # user hasn't composed one yet, seed silently from the same
        # default trip Odyssey ships with.
        base_trip = st.session_state.get("ody_last_trip")
        if base_trip is None or getattr(base_trip, "n_days", 0) == 0:
            seed_pois_nm = poi_df.to_dict("records") if not poi_df.empty else []
            _seed_days = ody.default_seed_trip(
                home_lat=float(my["lat"]), home_lon=float(my["lon"]),
                pois=seed_pois_nm, n_days=4,
            )
            try:
                base_trip = ody.compose_odyssey(
                    days=_seed_days,
                    incidents=inc_df.to_dict("records") if not inc_df.empty else [],
                    geofences=GEOFENCES,
                    pois=seed_pois_nm,
                )
            except Exception:
                base_trip = None

        if base_trip is None or getattr(base_trip, "n_days", 0) == 0:
            st.info(
                "Nomad needs an Odyssey trip to reflow.  Compose one in the "
                "**Odyssey** tab first, then come back here."
            )
        else:
            # ---- Live-state controls -------------------------------
            st.markdown(
                "**Where are you right now?**  Nomad reflows the "
                "*upcoming* days — every day at `current_day_idx` and "
                "beyond is re-scored under live signals; days before "
                "that stay frozen at their Odyssey baseline."
            )
            c_st1, c_st2, c_st3, c_st4 = st.columns([1, 1, 1, 1])
            with c_st1:
                nm_day_idx = int(st.number_input(
                    "Current day (1-based)",
                    min_value=1, max_value=base_trip.n_days,
                    value=int(st.session_state.get("nm_day_idx", 1)),
                    step=1, key="nm_day_idx",
                ))
            with c_st2:
                nm_mode = st.selectbox(
                    "Situational mode",
                    options=["at_start", "at_stay", "at_stop", "in_transit"],
                    index=["at_start", "at_stay", "at_stop", "in_transit"].index(
                        st.session_state.get("nm_mode", "at_stay")
                    ),
                    key="nm_mode",
                    help="Where the traveller physically is — shapes the advisory strip.",
                )
            with c_st3:
                nm_lat = float(st.number_input(
                    "Current lat", value=float(
                        st.session_state.get("nm_lat",
                            base_trip.days[min(nm_day_idx - 1, base_trip.n_days - 1)].day.stay_lat)
                    ),
                    format="%.5f", key="nm_lat",
                ))
            with c_st4:
                nm_lon = float(st.number_input(
                    "Current lon", value=float(
                        st.session_state.get("nm_lon",
                            base_trip.days[min(nm_day_idx - 1, base_trip.n_days - 1)].day.stay_lon)
                    ),
                    format="%.5f", key="nm_lon",
                ))

            # ---- Live-signal simulator -----------------------------
            with st.expander(
                "Live-signal simulator — inject fresh incidents on an upcoming corridor",
                expanded=False,
            ):
                st.caption(
                    "In a production deployment, live signals arrive from a "
                    "stream.  Here you can inject synthetic incidents to see "
                    "how Nomad reflows.  The injected incidents are added to "
                    "the current pool for this run only."
                )
                cs1, cs2, cs3 = st.columns([1, 1, 1])
                inj_day = cs1.number_input(
                    "Inject on day (1-based)", min_value=1,
                    max_value=base_trip.n_days,
                    value=int(st.session_state.get("nm_inj_day", min(base_trip.n_days, nm_day_idx + 1))),
                    step=1, key="nm_inj_day",
                )
                inj_count = cs2.number_input(
                    "How many incidents?", min_value=0, max_value=40,
                    value=int(st.session_state.get("nm_inj_count", 8)),
                    step=1, key="nm_inj_count",
                )
                inj_severity = cs3.selectbox(
                    "Severity",
                    options=[1, 2, 3, 4, 5],
                    index=int(st.session_state.get("nm_inj_severity", 3)) - 1,
                    key="nm_inj_severity",
                )

            # Build the live incidents pool: base + injected (if any)
            base_incidents = inc_df.to_dict("records") if not inc_df.empty else []
            live_incidents_list = list(base_incidents)
            inj_count_val = int(st.session_state.get("nm_inj_count", 0) or 0)
            inj_day_val = int(st.session_state.get("nm_inj_day", 1) or 1)
            inj_sev_val = int(st.session_state.get("nm_inj_severity", 3) or 3)
            if inj_count_val > 0 and 1 <= inj_day_val <= base_trip.n_days:
                inj_day_report = base_trip.days[inj_day_val - 1]
                inj_day_obj = inj_day_report.day
                if inj_day_obj.stops:
                    inj_center_lat = inj_day_obj.stops[0].lat
                    inj_center_lon = inj_day_obj.stops[0].lon
                else:
                    inj_center_lat = inj_day_obj.stay_lat
                    inj_center_lon = inj_day_obj.stay_lon
                for k in range(inj_count_val):
                    live_incidents_list.append({
                        "id": f"nomad-inj-day{inj_day_val}-{k}",
                        "lat": inj_center_lat + 0.0005 * k,
                        "lon": inj_center_lon + 0.0005 * k,
                        "category": "theft",
                        "severity": inj_sev_val,
                        "time": datetime.utcnow().isoformat(),
                        "title": f"Synthetic incident on {inj_day_obj.label}",
                        "created_at": datetime.utcnow().isoformat(),
                        "status": "verified",
                    })

            # ---- Compose reflow ------------------------------------
            state = nmd.NomadState(
                current_day_idx=nm_day_idx - 1,
                mode=nm_mode,
                current_lat=nm_lat,
                current_lon=nm_lon,
                elapsed_hours=24.0 * (nm_day_idx - 1),
            )
            # Candidate POIs for STOP_SUB — sourced from the full POI pool
            # near the *worst* upcoming day's centroid.
            center_lat = base_trip.days[min(nm_day_idx - 1, base_trip.n_days - 1)].day.stay_lat
            center_lon = base_trip.days[min(nm_day_idx - 1, base_trip.n_days - 1)].day.stay_lon
            nm_pois_list = poi_df.to_dict("records") if not poi_df.empty else []
            candidate_pois = nmd.candidate_pois_from_pois(
                nm_pois_list, center_lat, center_lon,
            )
            candidate_stays = []
            try:
                stays_df_local = load_csv("stays.csv")
                if stays_df_local is not None and not stays_df_local.empty:
                    candidate_stays = stays_df_local.to_dict("records")
            except Exception:
                candidate_stays = []

            reflow = nmd.compose_nomad_reflow(
                trip=base_trip,
                state=state,
                incidents=live_incidents_list,
                geofences=GEOFENCES,
                pois=nm_pois_list,
                candidate_pois=candidate_pois,
                candidate_stays=candidate_stays,
            )
            st.session_state.nm_last_reflow = reflow

            # ---- Verdict ribbon: baseline → live → reflowed --------
            _band_to_color = {
                "Serene":  "#53E3A6", "Solid":   "#7BC5F1",
                "Bumpy":   "#F9C440", "Fragile": "#FF9F43",
                "Critical":"#FF3D60", "empty":   "#6b7280",
            }
            base_hue = _band_to_color.get(reflow.baseline_verdict, "#7BC5F1")
            live_hue = _band_to_color.get(reflow.live_verdict, "#7BC5F1")
            refl_hue = _band_to_color.get(reflow.reflowed_verdict, "#7BC5F1")
            live_delta = reflow.live_trip_score - reflow.baseline_trip_score
            refl_delta = reflow.reflowed_trip_score - reflow.live_trip_score
            arrow_live = "→" if abs(live_delta) < 1 else ("↗" if live_delta > 0 else "↘")
            arrow_refl = "→" if abs(refl_delta) < 1 else ("↗" if refl_delta > 0 else "↘")
            st.markdown(
                f"""
                <div style="display:grid;grid-template-columns:1fr auto 1fr auto 1fr;gap:12px;align-items:center;margin:16px 0;padding:16px;border-radius:14px;background:rgba(15,23,42,0.35);border:1px solid rgba(148,163,184,0.15);">
                  <div style="text-align:center;">
                    <div style="font-size:11px;letter-spacing:1px;color:#94a3b8;text-transform:uppercase;">Baseline · Odyssey</div>
                    <div style="font-size:38px;font-weight:800;color:{base_hue};line-height:1;margin-top:6px;">{reflow.baseline_trip_score}</div>
                    <div style="font-size:13px;color:{base_hue};font-weight:600;">{reflow.baseline_verdict}</div>
                  </div>
                  <div style="font-size:24px;color:#94a3b8;font-weight:600;">{arrow_live}</div>
                  <div style="text-align:center;">
                    <div style="font-size:11px;letter-spacing:1px;color:#94a3b8;text-transform:uppercase;">Live · under current signals</div>
                    <div style="font-size:38px;font-weight:800;color:{live_hue};line-height:1;margin-top:6px;">{reflow.live_trip_score}</div>
                    <div style="font-size:13px;color:{live_hue};font-weight:600;">{reflow.live_verdict}  <span style="font-weight:400;color:#94a3b8;">({live_delta:+d})</span></div>
                  </div>
                  <div style="font-size:24px;color:#94a3b8;font-weight:600;">{arrow_refl}</div>
                  <div style="text-align:center;">
                    <div style="font-size:11px;letter-spacing:1px;color:#94a3b8;text-transform:uppercase;">Reflowed · best strategy</div>
                    <div style="font-size:38px;font-weight:800;color:{refl_hue};line-height:1;margin-top:6px;">{reflow.reflowed_trip_score}</div>
                    <div style="font-size:13px;color:{refl_hue};font-weight:600;">{reflow.reflowed_verdict}  <span style="font-weight:400;color:#94a3b8;">({refl_delta:+d})</span></div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # ---- Trigger + shortfall tile row ----------------------
            trg_c1, trg_c2, trg_c3, trg_c4 = st.columns(4)
            trg_c1.metric(
                "Shortfall vs baseline",
                f"{reflow.projected_shortfall:+.1f} pts",
                help="Baseline trip score minus live trip score. Positive means the trip has degraded.",
            )
            trg_c2.metric(
                "Reflow trigger",
                "ACTIVE" if reflow.reflow_triggered else "quiet",
                delta=f"threshold {nmd.SHORTFALL_TRIGGER_PTS:.0f} pts",
                delta_color="off",
            )
            trg_c3.metric(
                "Degraded upcoming days",
                f"{reflow.signals.degraded_days}",
                delta=f"≥ {nmd.DAY_DEGRADE_PTS:.0f} pt loss",
                delta_color="off",
            )
            trg_c4.metric(
                "Incidents on corridors",
                f"{reflow.signals.corridor_incidents_new}",
                delta=f"across {reflow.signals.days_with_new_incidents} days",
                delta_color="off",
            )

            st.markdown(
                f"<div style='padding:10px 14px;border-radius:10px;background:rgba(15,23,42,0.35);"
                f"border-left:3px solid {live_hue};margin:6px 0 12px 0;font-size:14px;'>"
                f"<b>Signals trigger:</b> {reflow.signals.trigger_summary}</div>",
                unsafe_allow_html=True,
            )

            # ---- Recommendation callout ----------------------------
            best = reflow.best_strategy
            best_verdict_hue = _band_to_color.get(best.projected_verdict, "#7BC5F1")
            st.markdown('<div style="font-size:15px;font-weight:700;color:#e2e8f0;margin:14px 0 8px 0;">Recommendation</div>', unsafe_allow_html=True)
            st.markdown(
                f"""
                <div style="padding:18px 20px;border-radius:14px;background:linear-gradient(135deg,rgba(15,23,42,0.55),rgba(30,41,59,0.55));border:1px solid {best_verdict_hue}55;box-shadow:0 0 28px {best_verdict_hue}22;">
                  <div style="display:flex;align-items:baseline;gap:14px;flex-wrap:wrap;">
                    <span style="font-size:11px;letter-spacing:1.5px;padding:3px 10px;border-radius:999px;background:{best_verdict_hue}22;color:{best_verdict_hue};font-weight:700;text-transform:uppercase;">{best.kind}</span>
                    <span style="font-size:18px;font-weight:700;color:#f8fafc;">{best.label}</span>
                    <span style="margin-left:auto;font-size:26px;font-weight:800;color:{best_verdict_hue};">
                      {best.projected_trip_score}<span style="color:#94a3b8;font-size:14px;font-weight:600;">/100</span>
                    </span>
                    <span style="font-size:13px;font-weight:700;color:{'#53E3A6' if best.uplift_pts > 0 else '#94a3b8'};">
                      uplift {best.uplift_pts:+.1f} pts → {best.projected_verdict}
                    </span>
                  </div>
                  <div style="margin-top:10px;color:#cbd5e1;font-size:13.5px;line-height:1.5;">{best.detail}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # ---- Live day cards -----------------------------------
            if reflow.live_days:
                st.markdown('<div style="font-size:15px;font-weight:700;color:#e2e8f0;margin:20px 0 8px 0;">Upcoming days — live re-score</div>', unsafe_allow_html=True)
                day_cols = st.columns(max(1, len(reflow.live_days)))
                for j, ld in enumerate(reflow.live_days):
                    with day_cols[j]:
                        d_hue = _band_to_color.get(ld.live_band, "#7BC5F1")
                        deg_badge = ""
                        if ld.degrade_flag:
                            deg_badge = "<span style='display:inline-block;padding:1px 7px;font-size:10px;font-weight:700;border-radius:999px;background:#FF3D6033;color:#FF3D60;margin-left:6px;'>DEGRADED</span>"
                        elif ld.delta_score >= nmd.DAY_DEGRADE_PTS:
                            deg_badge = "<span style='display:inline-block;padding:1px 7px;font-size:10px;font-weight:700;border-radius:999px;background:#53E3A633;color:#53E3A6;margin-left:6px;'>IMPROVED</span>"
                        delta_arrow = "→" if abs(ld.delta_score) < 0.5 else ("↗" if ld.delta_score > 0 else "↘")
                        delta_color = "#53E3A6" if ld.delta_score > 0 else ("#FF9F43" if ld.delta_score < 0 else "#94a3b8")
                        st.markdown(
                            f"""
                            <div style="padding:14px;border-radius:12px;background:rgba(15,23,42,0.5);border:1px solid {d_hue}44;">
                              <div style="font-size:11px;color:#94a3b8;letter-spacing:1px;text-transform:uppercase;">Day {ld.day_index+1} {deg_badge}</div>
                              <div style="font-size:13px;font-weight:600;color:#e2e8f0;margin-top:4px;line-height:1.3;">{ld.day_label}</div>
                              <div style="display:flex;align-items:baseline;gap:8px;margin-top:10px;">
                                <span style="font-size:11px;color:#94a3b8;">baseline</span>
                                <span style="font-size:15px;color:#cbd5e1;font-weight:600;">{ld.baseline_score}</span>
                                <span style="margin:0 4px;color:#64748b;">{delta_arrow}</span>
                                <span style="font-size:24px;font-weight:800;color:{d_hue};">{ld.live_score}</span>
                              </div>
                              <div style="font-size:12px;color:{delta_color};font-weight:600;margin-top:2px;">Δ {ld.delta_score:+.0f} pts · {ld.corridor_incidents_new} incident{'s' if ld.corridor_incidents_new != 1 else ''}</div>
                              <div style="font-size:11px;color:#94a3b8;margin-top:8px;line-height:1.35;">{ld.reason}</div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

            # ---- Strategies table --------------------------------
            st.markdown('<div style="font-size:15px;font-weight:700;color:#e2e8f0;margin:20px 0 8px 0;">Ranked reflow strategies</div>', unsafe_allow_html=True)
            for k_i, sr in enumerate(reflow.strategies):
                sr_hue = _band_to_color.get(sr.projected_verdict, "#7BC5F1")
                is_best = (sr.kind == best.kind and sr.day_index == best.day_index and sr.uplift_pts == best.uplift_pts)
                ring = f"box-shadow:0 0 22px {sr_hue}55;border:2px solid {sr_hue};" if is_best else "border:1px solid rgba(148,163,184,0.15);"
                uplift_color = "#53E3A6" if sr.uplift_pts > 0 else ("#94a3b8" if sr.uplift_pts == 0 else "#FF9F43")
                # Compute a horizontal uplift bar (px width up to ~140 for a 20pt uplift)
                bar_pct = min(100, max(0, int(round((sr.uplift_pts + 5) * 8))))
                st.markdown(
                    f"""
                    <div style="padding:12px 16px;margin:6px 0;border-radius:10px;background:rgba(15,23,42,0.4);{ring}">
                      <div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;">
                        <span style="font-size:10px;letter-spacing:1.4px;padding:2px 8px;border-radius:999px;background:{sr_hue}22;color:{sr_hue};font-weight:800;text-transform:uppercase;">{sr.kind}</span>
                        <span style="font-size:14px;font-weight:600;color:#e2e8f0;">{sr.label}</span>
                        <span style="margin-left:auto;font-size:20px;font-weight:800;color:{sr_hue};">
                          {sr.projected_trip_score}
                          <span style="color:#94a3b8;font-size:11px;font-weight:600;">/100 · {sr.projected_verdict}</span>
                        </span>
                        <span style="font-size:12px;color:{uplift_color};font-weight:700;min-width:80px;text-align:right;">{sr.uplift_pts:+.1f} pts</span>
                      </div>
                      <div style="margin-top:6px;height:3px;background:rgba(148,163,184,0.12);border-radius:2px;overflow:hidden;">
                        <div style="height:100%;width:{bar_pct}%;background:linear-gradient(90deg,{sr_hue}88,{sr_hue});"></div>
                      </div>
                      <div style="margin-top:6px;font-size:12.5px;color:#cbd5e1;line-height:1.45;">{sr.detail}</div>
                      <div style="margin-top:4px;font-size:11px;color:#94a3b8;">
                        kept stops <b>{sr.total_stops_kept}</b> · risk-km <b>{sr.total_risk_km:.2f}</b> · distance <b>{sr.total_distance_km:.1f} km</b>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

            # ---- Advisory strip -----------------------------------
            st.markdown('<div style="font-size:15px;font-weight:700;color:#e2e8f0;margin:20px 0 8px 0;">Advisory</div>', unsafe_allow_html=True)
            for a_line in reflow.advisory:
                st.markdown(
                    f"<div style='padding:8px 12px;margin:4px 0;border-radius:8px;background:rgba(15,23,42,0.35);border-left:2px solid {live_hue};font-size:13px;color:#e2e8f0;'>{a_line}</div>",
                    unsafe_allow_html=True,
                )

            # ---- Export ------------------------------------------
            st.markdown("---")
            ex_c1, ex_c2 = st.columns(2)
            with ex_c1:
                st.download_button(
                    "Download JSON (waysafe.nomad.v1)",
                    data=nmd.to_json(reflow),
                    file_name="waysafe_nomad.json",
                    mime="application/json",
                    use_container_width=True,
                )
            with ex_c2:
                st.download_button(
                    "Download Markdown reflow brief",
                    data=nmd.to_markdown(reflow),
                    file_name="waysafe_nomad.md",
                    mime="text/markdown",
                    use_container_width=True,
                )

            t_nmd_md, t_nmd_json = st.tabs(["Markdown preview", "JSON preview"])
            with t_nmd_md:
                st.markdown(nmd.to_markdown(reflow))
            with t_nmd_json:
                st.code(nmd.to_json(reflow, indent=2), language="json")

    # ---------------- Convoy — Group Consensus Reflow (Day 86)
    # Odyssey composes for a single implied traveller.  Nomad reflows
    # what remains of that trip live.  Neither answers the question a
    # tour lead or family planner asks the moment they have two or more
    # people on the same itinerary: *"is Nomad's recommendation the
    # right move for **every member** of my group, or only for the
    # abstract mean?"*  Convoy composes per-member day scores,
    # re-scores every Nomad strategy as a ballot across the members,
    # and picks the one that best balances mean uplift with worst-case
    # uplift while honouring vulnerable-member vetoes and per-member
    # day locks.  Same physics, zero new measurements.
    with tabs[21]:
        st.subheader("Convoy — Group Consensus Reflow")
        st.caption(
            "Odyssey and Nomad both assume the trip is being lived by *one* person. "
            "Convoy lifts that assumption. Every convoy member carries a personal "
            "risk-tolerance, curfew, mobility and medical stack; every Nomad "
            "strategy is re-scored as a ballot across the members; the winner is "
            "the admissible strategy that maximises "
            "**0.60·mean_uplift + 0.40·worst_uplift** without triggering a "
            "vulnerable-member veto."
        )

        base_trip = st.session_state.get("ody_last_trip")
        base_reflow = st.session_state.get("nm_last_reflow")

        if base_trip is None or getattr(base_trip, "n_days", 0) == 0:
            st.info(
                "Convoy needs an Odyssey trip and a Nomad reflow to work with. "
                "Compose one in **Odyssey**, then step through **Nomad** to "
                "produce a reflow — come back here."
            )
        elif base_reflow is None:
            st.info(
                "Compose a Nomad reflow in the **Nomad** tab first — Convoy "
                "runs on top of the strategy shortlist Nomad has already "
                "simulated."
            )
        else:
            # ---- Roster editor -------------------------------------
            if "convoy_roster" not in st.session_state:
                seed = cvy.default_seed_convoy()
                st.session_state.convoy_roster = [
                    {
                        "id": m.id,
                        "name": m.name,
                        "age_band": m.profile.age_band,
                        "mobility": m.profile.mobility,
                        "risk_tolerance": m.profile.risk_tolerance,
                        "curfew_hour": m.profile.curfew_hour,
                        "medical_flags": ", ".join(m.profile.medical_flags),
                        "locked_day_indices": ", ".join(
                            str(i + 1) for i in m.profile.locked_day_indices
                        ),
                    }
                    for m in seed.members
                ]

            with st.expander(
                "Convoy roster — edit member profiles",
                expanded=False,
            ):
                st.caption(
                    "One row per member. `risk_tolerance` ∈ [0, 1] · "
                    "`curfew_hour` ∈ [17, 26] (26 = no curfew) · "
                    "`medical_flags` comma-separated (cardiac, respiratory, "
                    "pregnancy, diabetes, medication, mobility_aid, "
                    "cold_sensitivity, allergy) · `locked_day_indices` "
                    "1-based, comma-separated — days this member can't afford "
                    "to have altered."
                )
                _roster_df = pd.DataFrame(st.session_state.convoy_roster)
                edited = st.data_editor(
                    _roster_df,
                    key="convoy_roster_editor",
                    use_container_width=True, num_rows="dynamic",
                    column_config={
                        "id": st.column_config.TextColumn("id", width="small"),
                        "name": st.column_config.TextColumn("name", width="medium"),
                        "age_band": st.column_config.SelectboxColumn(
                            "age_band",
                            options=["child", "teen", "adult", "senior"],
                            width="small",
                        ),
                        "mobility": st.column_config.SelectboxColumn(
                            "mobility",
                            options=["low", "moderate", "high"],
                            width="small",
                        ),
                        "risk_tolerance": st.column_config.NumberColumn(
                            "risk_tolerance", min_value=0.0, max_value=1.0,
                            step=0.05, format="%.2f",
                        ),
                        "curfew_hour": st.column_config.NumberColumn(
                            "curfew_hour", min_value=17, max_value=26,
                            step=1, format="%d",
                        ),
                        "medical_flags": st.column_config.TextColumn(
                            "medical_flags", width="medium",
                        ),
                        "locked_day_indices": st.column_config.TextColumn(
                            "locked_day_indices", width="small",
                        ),
                    },
                )
                st.session_state.convoy_roster = edited.to_dict("records")

            convoy_id = st.session_state.get(
                "convoy_id",
                "convoy-" + str(int(pd.Timestamp.utcnow().timestamp())),
            )
            st.session_state.convoy_id = convoy_id
            convoy_name = st.text_input(
                "Convoy name",
                value=st.session_state.get(
                    "convoy_name",
                    "Family loop — 2 adults + child + senior",
                ),
                key="convoy_name",
            )

            members = cvy.members_from_editor_rows(st.session_state.convoy_roster)
            if not members:
                st.warning(
                    "Add at least one member with a name to see a consensus."
                )
            else:
                convoy_obj = cvy.Convoy(
                    id=convoy_id, name=convoy_name, members=members,
                )

                # ---- Compose -------------------------------------
                convoy_incidents = st.session_state.get(
                    "nm_live_incidents",
                    inc_df.to_dict("records") if not inc_df.empty else [],
                )
                convoy_report = cvy.compose_convoy_report(
                    convoy=convoy_obj,
                    trip=base_trip,
                    reflow=base_reflow,
                    incidents=convoy_incidents,
                    geofences=GEOFENCES,
                    pois=poi_df.to_dict("records") if not poi_df.empty else [],
                )

                _band_to_color = {
                    "Serene": "#53E3A6", "Solid": "#7BC5F1",
                    "Bumpy": "#F9C440", "Fragile": "#FF9F43",
                    "Critical": "#FF3D60", "empty": "#6b7280",
                }

                # ---- Convoy verdict transition -------------------
                cb_hue = _band_to_color.get(
                    convoy_report.convoy_baseline_band, "#7BC5F1"
                )
                cf_hue = _band_to_color.get(
                    convoy_report.consensus_final_band, "#7BC5F1"
                )
                base_mean = convoy_report.convoy_mean_personal_baseline
                base_worst = convoy_report.convoy_worst_personal_baseline
                final_mean = convoy_report.consensus_final_mean
                final_worst = convoy_report.consensus_final_worst
                dm = convoy_report.consensus_delta_mean
                dw = convoy_report.consensus_delta_worst
                arrow = "→" if abs(dm) < 0.5 else ("↗" if dm > 0 else "↘")
                st.markdown(
                    f"""
                    <div style="display:grid;grid-template-columns:1fr auto 1fr;gap:14px;align-items:center;margin:16px 0;padding:18px;border-radius:14px;background:rgba(15,23,42,0.35);border:1px solid rgba(148,163,184,0.15);">
                      <div style="text-align:center;">
                        <div style="font-size:11px;letter-spacing:1.4px;color:#94a3b8;text-transform:uppercase;">Convoy · STAY_COURSE</div>
                        <div style="display:flex;gap:14px;justify-content:center;align-items:baseline;margin-top:8px;">
                          <div>
                            <div style="font-size:10px;color:#94a3b8;letter-spacing:1px;">MEAN</div>
                            <div style="font-size:34px;font-weight:800;color:{cb_hue};line-height:1;">{base_mean:.0f}</div>
                          </div>
                          <div>
                            <div style="font-size:10px;color:#94a3b8;letter-spacing:1px;">WORST</div>
                            <div style="font-size:34px;font-weight:800;color:{cb_hue};line-height:1;">{base_worst}</div>
                          </div>
                        </div>
                        <div style="font-size:12px;color:{cb_hue};font-weight:600;margin-top:6px;">{convoy_report.convoy_baseline_band}</div>
                      </div>
                      <div style="font-size:26px;color:#94a3b8;font-weight:600;">{arrow}</div>
                      <div style="text-align:center;">
                        <div style="font-size:11px;letter-spacing:1.4px;color:#94a3b8;text-transform:uppercase;">Convoy · under consensus <b style='color:#e2e8f0;'>{convoy_report.consensus_ballot.strategy_kind}</b></div>
                        <div style="display:flex;gap:14px;justify-content:center;align-items:baseline;margin-top:8px;">
                          <div>
                            <div style="font-size:10px;color:#94a3b8;letter-spacing:1px;">MEAN</div>
                            <div style="font-size:34px;font-weight:800;color:{cf_hue};line-height:1;">{final_mean:.0f} <span style='font-size:12px;color:#94a3b8;font-weight:600;'>({dm:+.1f})</span></div>
                          </div>
                          <div>
                            <div style="font-size:10px;color:#94a3b8;letter-spacing:1px;">WORST</div>
                            <div style="font-size:34px;font-weight:800;color:{cf_hue};line-height:1;">{final_worst} <span style='font-size:12px;color:#94a3b8;font-weight:600;'>({dw:+.0f})</span></div>
                          </div>
                        </div>
                        <div style="font-size:12px;color:{cf_hue};font-weight:600;margin-top:6px;">{convoy_report.consensus_final_band}</div>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                # ---- Rollup lines --------------------------------
                for L in convoy_report.convoy_summary_lines:
                    st.markdown(
                        f"<div style='padding:8px 14px;margin:4px 0;border-radius:8px;background:rgba(15,23,42,0.35);border-left:3px solid {cf_hue};font-size:13.5px;color:#e2e8f0;line-height:1.5;'>{L}</div>",
                        unsafe_allow_html=True,
                    )

                # ---- Member cards --------------------------------
                st.markdown(
                    '<div style="font-size:15px;font-weight:700;color:#e2e8f0;margin:18px 0 8px 0;">Members — personal trip under STAY_COURSE</div>',
                    unsafe_allow_html=True,
                )
                m_cols = st.columns(min(4, max(1, len(members))))
                for j, (m, p) in enumerate(zip(convoy_obj.members, convoy_report.member_personal_baselines)):
                    with m_cols[j % len(m_cols)]:
                        p_hue = _band_to_color.get(p.trip_band, "#7BC5F1")
                        v = cvy._vulnerability(m.profile)
                        vuln_pct = int(v * 100)
                        flags_str = (
                            ", ".join(m.profile.medical_flags)
                            if m.profile.medical_flags else "no medical flags"
                        )
                        st.markdown(
                            f"""
                            <div style="padding:14px;border-radius:12px;background:rgba(15,23,42,0.5);border:1px solid {p_hue}44;">
                              <div style="display:flex;justify-content:space-between;align-items:baseline;">
                                <div style="font-size:14px;font-weight:700;color:#f8fafc;">{m.name}</div>
                                <span style="font-size:10px;letter-spacing:1px;padding:2px 8px;border-radius:999px;background:{p_hue}22;color:{p_hue};font-weight:700;">{p.trip_band}</span>
                              </div>
                              <div style="font-size:11px;color:#94a3b8;margin-top:2px;">{m.profile.age_band} · mobility {m.profile.mobility} · rt {m.profile.risk_tolerance:.2f} · curfew {m.profile.curfew_hour}:00</div>
                              <div style="font-size:11px;color:#94a3b8;margin-top:2px;">{flags_str}</div>
                              <div style="font-size:36px;font-weight:800;color:{p_hue};line-height:1;margin-top:10px;">{p.trip_score}<span style='font-size:12px;color:#94a3b8;font-weight:600;'>/100</span></div>
                              <div style="font-size:11px;color:#94a3b8;margin-top:2px;">mean {p.mean_day:.0f} · min {p.min_day}</div>
                              <div style="height:4px;margin-top:8px;background:rgba(148,163,184,0.15);border-radius:2px;overflow:hidden;">
                                <div style="height:100%;width:{vuln_pct}%;background:linear-gradient(90deg,#F9C44088,#FF9F43);"></div>
                              </div>
                              <div style="font-size:10px;color:#94a3b8;margin-top:2px;letter-spacing:0.5px;">vulnerability {v:.2f}</div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                # ---- Ballots panel -------------------------------
                st.markdown(
                    '<div style="font-size:15px;font-weight:700;color:#e2e8f0;margin:20px 0 8px 0;">Strategy ballots — consensus uplift ranked</div>',
                    unsafe_allow_html=True,
                )
                for b in convoy_report.ballots:
                    hint_color = {
                        "consensus": "#53E3A6",
                        "baseline": "#7BC5F1",
                        "dissent": "#F9C440",
                        "veto": "#FF3D60",
                    }.get(b.rank_hint, "#94a3b8")
                    is_winner = (
                        b.strategy_kind == convoy_report.consensus_ballot.strategy_kind
                        and b.strategy_day_index
                        == convoy_report.consensus_ballot.strategy_day_index
                    )
                    ring = (
                        f"box-shadow:0 0 22px {hint_color}55;border:2px solid {hint_color};"
                        if is_winner
                        else "border:1px solid rgba(148,163,184,0.15);"
                    )
                    id_to_name = {m.id: m.name for m in convoy_obj.members}
                    chip_html = ""
                    for v in b.votes:
                        chip_bg = "#FF3D60" if v.is_veto else (
                            "#F9C440" if v.is_dissent else (
                                "#53E3A6" if v.uplift >= 1 else "#7BC5F1"
                            )
                        )
                        chip_html += (
                            f"<span style='display:inline-block;padding:3px 8px;"
                            f"margin:2px 3px 2px 0;border-radius:999px;"
                            f"font-size:11px;font-weight:700;background:{chip_bg}22;"
                            f"color:{chip_bg};border:1px solid {chip_bg}55;'>"
                            f"{id_to_name.get(v.member_id, v.member_id)} "
                            f"{v.uplift:+.0f}</span>"
                        )
                    st.markdown(
                        f"""
                        <div style="padding:12px 16px;margin:8px 0;border-radius:10px;background:rgba(15,23,42,0.4);{ring}">
                          <div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;">
                            <span style="font-size:10px;letter-spacing:1.4px;padding:2px 8px;border-radius:999px;background:{hint_color}22;color:{hint_color};font-weight:800;text-transform:uppercase;">{b.strategy_kind}</span>
                            <span style="font-size:14px;font-weight:600;color:#e2e8f0;">{b.strategy_label}</span>
                            <span style="margin-left:auto;font-size:20px;font-weight:800;color:{hint_color};">
                              {b.consensus_uplift:+.1f}<span style='font-size:11px;color:#94a3b8;font-weight:600;'> pts</span>
                            </span>
                          </div>
                          <div style="margin-top:6px;font-size:12.5px;color:#cbd5e1;line-height:1.45;">{b.strategy_detail}</div>
                          <div style="margin-top:8px;">{chip_html}</div>
                          <div style="margin-top:4px;font-size:11px;color:#94a3b8;">
                            mean {b.mean_uplift:+.1f} · worst {b.worst_uplift:+.1f} · dissenters {b.n_dissent}/{b.dissent_tolerance} · vetoes {b.n_veto} · {'admissible' if b.is_admissible else 'inadmissible — falls back to STAY_COURSE'}
                          </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                # ---- Personalised advisories ---------------------
                st.markdown(
                    '<div style="font-size:15px;font-weight:700;color:#e2e8f0;margin:20px 0 8px 0;">Personalised advisories</div>',
                    unsafe_allow_html=True,
                )
                id_to_name = {m.id: m.name for m in convoy_obj.members}
                id_to_band = {
                    p.member_id: p.trip_band
                    for p in convoy_report.member_personal_baselines
                }
                for mid, adv_lines in convoy_report.per_member_advisories:
                    band = id_to_band.get(mid, "Solid")
                    a_hue = _band_to_color.get(band, "#7BC5F1")
                    body = "".join(
                        f"<div style='padding:6px 0;font-size:13px;color:#e2e8f0;line-height:1.5;'>{L}</div>"
                        for L in adv_lines
                    )
                    st.markdown(
                        f"""
                        <div style="padding:12px 16px;margin:6px 0;border-radius:10px;background:rgba(15,23,42,0.35);border-left:3px solid {a_hue};">
                          <div style="font-size:11px;letter-spacing:1px;color:#94a3b8;text-transform:uppercase;">{id_to_name.get(mid, mid)}</div>
                          {body}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                # ---- Export --------------------------------------
                st.markdown("---")
                ex_c1, ex_c2 = st.columns(2)
                with ex_c1:
                    st.download_button(
                        "Download JSON (waysafe.convoy.v1)",
                        data=cvy.to_json(convoy_report),
                        file_name="waysafe_convoy.json",
                        mime="application/json",
                        use_container_width=True,
                    )
                with ex_c2:
                    st.download_button(
                        "Download Markdown consensus brief",
                        data=cvy.to_markdown(convoy_report),
                        file_name="waysafe_convoy.md",
                        mime="text/markdown",
                        use_container_width=True,
                    )

                t_cvy_md, t_cvy_json = st.tabs(["Markdown preview", "JSON preview"])
                with t_cvy_md:
                    st.markdown(cvy.to_markdown(convoy_report))
                with t_cvy_json:
                    st.code(cvy.to_json(convoy_report, indent=2), language="json")

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
