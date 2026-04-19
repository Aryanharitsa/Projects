
import streamlit as st
import pandas as pd
import pydeck as pdk
import json, uuid, io, base64
from datetime import datetime
from pathlib import Path
from PIL import Image
from utils import haversine_km, point_in_polygon, sha256_hex, build_merkle
from safety import compute_safety, heatmap_points
from theme import inject_theme, render_brand, render_score_card, band_color

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

with st.sidebar:
    render_brand()
role = st.sidebar.radio("View", ["Tourist App", "Authority Dashboard", "Merkle Auditor"], label_visibility="collapsed")
st.sidebar.caption(f"Session user · `{st.session_state.user}`")

with st.sidebar.expander("Location & Demo Controls", expanded=True):
    st.session_state.offline = st.checkbox("Offline mode (simulate no network)", value=st.session_state.offline)
    lat = st.number_input("Your lat", value=float(st.session_state.current_loc["lat"]), format="%.6f")
    lon = st.number_input("Your lon", value=float(st.session_state.current_loc["lon"]), format="%.6f")
    if st.button("Update location", type="primary", use_container_width=True):
        st.session_state.current_loc = {"lat": lat, "lon": lon}
    st.caption("Tip: 15.55,73.76 (Baga) · 15.49,73.78 (Aguada)")

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
    # load, mutate, save fresh copies to avoid global mutability
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

def draw_map_layers(incidents, broadcasts, pois, user_loc, *, show_heatmap=True):
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

    view_state = pdk.ViewState(latitude=user_loc["lat"], longitude=user_loc["lon"], zoom=12)
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

    tabs = st.tabs(["Map", "Report Hazard", "Alerts", "SOS", "Trip Report"])

    with tabs[0]:
        draw_map_layers(inc_df, bcast_df, poi_df, my, show_heatmap=st.session_state.show_heatmap)
        st.caption("🔴 verified incident · 🟡 pending · 🟢 help POI · 🟠 risk zone · 🔵 active broadcast")

    with tabs[1]:
        st.subheader("Report a Hazard")
        category = st.selectbox("Category", ["landslide","roadblock","accident","flooding","other"])
        note = st.text_area("Note (optional)")
        up = st.file_uploader("Photo (optional)", type=["jpg","jpeg","png"])
        if st.button("Submit (respects Offline mode)"):
            lat = st.session_state.current_loc["lat"]; lon = st.session_state.current_loc["lon"]
            ts = datetime.utcnow().isoformat()
            photo_path = ""; sha = ""
            if up:
                img = Image.open(up).convert("RGB")
                img_id = f"{uuid.uuid4().hex[:10]}.jpg"
                p = DATA / "uploads"; p.mkdir(exist_ok=True); img.save(p / img_id, "JPEG", quality=70, optimize=True)
                photo_path = f"data/uploads/{img_id}"
                with open(p / img_id, "rb") as fh:
                    sha = sha256_hex(fh.read() + f"{lat}{lon}{ts}".encode())
            else:
                sha = sha256_hex(f"{lat}{lon}{ts}".encode())
            row = {"id": str(uuid.uuid4()), "user": st.session_state.user, "lat": lat, "lon": lon,
                   "category": category, "note": note, "photo_path": photo_path, "sha256": sha,
                   "sig": f"sig-{st.session_state.user[:6]}", "status": "pending", "created_at": ts}
            if st.session_state.offline:
                st.session_state.outbox.append({"type": "incident", "row": row}); st.info("Saved offline (Queued • 1). Turn off Offline mode and click Sync.")
            else:
                inc_local = load_csv("incidents.csv")
                inc_local = pd.concat([inc_local, pd.DataFrame([row])], ignore_index=True); save_csv(inc_local, "incidents.csv")
                st.success("Incident submitted!")
                # refresh local
                inc_df = load_csv("incidents.csv")
        if st.button("Sync now"):
            applied = push_outbox()
            if applied: st.success(f"Synced {applied} queued items."); inc_df = load_csv("incidents.csv")

    with tabs[2]:
        st.subheader("Broadcast Alerts near you")
        my = st.session_state.current_loc
        if bcast_df.empty:
            st.info("No alerts yet.")
        else:
            nearby = []
            for _, r in bcast_df.iterrows():
                d = haversine_km(my["lat"], my["lon"], r["lat"], r["lon"])
                if d <= r["radius_km"]:
                    nearby.append(r)
            if nearby:
                for r in nearby:
                    st.error(f"ALERT: Verified {r['incident_id'][:6]} • within {r['radius_km']} km")
            else:
                st.success("No active alerts in your radius.")
        st.caption("Simulated WS via file updates.")

    with tabs[3]:
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
            my = st.session_state.current_loc
            # Correct distance calculation per row
            def _dist(row):
                return haversine_km(my["lat"], my["lon"], row["lat"], row["lon"])
            poi_local = load_csv("poi.csv")
            poi_local["dist_km"] = poi_local.apply(_dist, axis=1)
            st.write("Nearest help:"); st.table(poi_local.sort_values("dist_km").head(3)[["name","ptype","dist_km"]])

    with tabs[4]:
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
