"""Live Trip Companion engine for WaySafe.

Turns a static *planned* route into a *live* journey with proactive,
geo-aware alerts and a trusted-contacts broadcast loop. Pure-Python, no
new deps — composes on top of `routing`, `safety`, and `forecast`.

The journey is *simulated* against wall-clock time (a real GPS feed
slots into the same `tick()` call), so the demo runs entirely offline
while staying faithful to the production data path.

Core flow
---------

    1.  caller hands us a `RouteResult` from `routing.plan_*_route`
        plus current `incidents / geofences / pois`,
    2.  `start_trip()` snapshots the route into a `TripSession`,
    3.  every `tick()` advances the journey by `(dt · speed × factor)`,
        evaluates the path ahead, and emits `Alert`s when:

            *   risk on the next `LOOKAHEAD_KM` of path crosses
                `RISK_AHEAD_THRESHOLD` (=0.45), with the dominant
                category called out when the forecaster knows it,
            *   the traveler crosses *into* / *out of* a geofence,
            *   the traveler stalls (no progress) for
                `STALL_AUTO_SOS_MIN` minutes inside a high-risk zone —
                an *auto-SOS* fires (+ trusted-contact broadcasts),
            *   the trip starts (`departure`) or completes (`arrival`).

Alerts are deduped on `(kind, location_bucket)` within a
`ALERT_COOLDOWN_S` window so the same risk corridor doesn't spam.
Every fired alert can fan out to opted-in trusted contacts via
`Broadcast` rows persisted to `data/notifications.csv`.

State is a dataclass tree — `TripSession` holds the position, status,
alert log, milestones, and a tail-bounded heartbeat trace. Streamlit
keeps it in `st.session_state["trip"]`; nothing here imports streamlit.
"""
from __future__ import annotations

import csv
import math
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, List, Mapping, Optional, Sequence, Tuple

from utils import haversine_km, point_in_polygon
from safety import point_risk, CATEGORY_SEVERITY, HELP_POI_TYPES

# ---------------------------------------------------------------- constants


AVG_TRAVEL_KMH = 32.0                  # mirrors routing.AVG_TRAVEL_KMH
LOOKAHEAD_KM = 1.5                     # how far ahead we sample for warnings
RISK_AHEAD_THRESHOLD = 0.45            # raise risk_ahead at or above this
RISK_RECOVERY_THRESHOLD = 0.32         # below = recovery (hysteresis band)
ALERT_COOLDOWN_S = 90                  # dedupe identical alerts inside this
HEARTBEAT_KEEP = 240                   # bound the trace at ~one per second
STALL_AUTO_SOS_MIN = 5                 # min stalled in red zone before SOS
SAFER_NEAR_KM = 0.6                    # 'safer-segment-coming-up' lookahead
LOCATION_BUCKET_DEG = 0.001            # ~110 m — alert dedupe granularity


_ALERT_ICON = {
    "departure":     "🚦",
    "arrival":       "🏁",
    "risk_ahead":    "⚠️",
    "geofence_enter": "🚷",
    "geofence_exit":  "✅",
    "safer_segment": "🟢",
    "auto_sos":      "🆘",
    "stall":         "⏸️",
    "info":          "ℹ️",
}


_ALERT_TONE = {
    "info":      "info",
    "warn":      "warn",
    "critical":  "critical",
}


# ---------------------------------------------------------------- dataclasses


@dataclass
class Alert:
    id: str
    ts: datetime
    kind: str
    severity: str            # "info" | "warn" | "critical"
    message: str
    location: Tuple[float, float] | None = None
    lookahead_km: float | None = None
    payload: dict = field(default_factory=dict)

    @property
    def icon(self) -> str:
        return _ALERT_ICON.get(self.kind, "•")


@dataclass
class Milestone:
    ts: datetime
    kind: str                # "departure" | "geofence_enter" | "geofence_exit"
                             # | "auto_sos" | "stall" | "recover" | "arrival"
    summary: str
    payload: dict = field(default_factory=dict)


@dataclass
class TripPlan:
    """Snapshot of a `RouteResult` we keep frozen for the whole journey."""
    route_mode: str
    coords: List[Tuple[float, float]]
    cum_km: List[float]                  # prefix-sum, len == len(coords)
    distance_km: float
    eta_minutes: float
    avg_safety: int
    min_safety: int
    notes: List[str]
    origin_label: str = "Start"
    dest_label: str = "Destination"
    depart_at: datetime | None = None


@dataclass
class TrustedContact:
    id: str
    name: str
    contact: str             # phone or email — opaque string for the demo
    relationship: str = "friend"
    opt_in: List[str] = field(default_factory=lambda: ["departure", "arrival", "auto_sos"])

    @classmethod
    def from_row(cls, row: Mapping) -> "TrustedContact":
        return cls(
            id=str(row.get("id") or uuid.uuid4().hex[:8]),
            name=str(row.get("name", "")).strip() or "Trusted contact",
            contact=str(row.get("contact", "")).strip(),
            relationship=str(row.get("relationship", "friend")).strip() or "friend",
            opt_in=[s.strip() for s in str(row.get("opt_in", "departure,arrival,auto_sos")).split(",") if s.strip()],
        )


@dataclass
class Broadcast:
    """A simulated SMS/notification dispatch — also persisted to CSV."""
    id: str
    ts: datetime
    trip_id: str
    contact_id: str
    contact_name: str
    contact: str
    kind: str               # mirrors Alert.kind
    body: str

    def to_row(self) -> dict:
        return {
            "id": self.id,
            "ts": self.ts.isoformat(timespec="seconds"),
            "trip_id": self.trip_id,
            "contact_id": self.contact_id,
            "contact_name": self.contact_name,
            "contact": self.contact,
            "kind": self.kind,
            "body": self.body,
        }


@dataclass
class TripSession:
    trip_id: str
    plan: TripPlan
    started_at: datetime
    status: str = "active"               # "active" | "paused" | "completed" | "cancelled"
    speed_factor: float = 4.0            # 4× sim by default — feels alive
    km_travelled: float = 0.0
    last_tick_at: datetime | None = None
    alerts: List[Alert] = field(default_factory=list)
    milestones: List[Milestone] = field(default_factory=list)
    heartbeats: List[Tuple[datetime, float, float, float]] = field(default_factory=list)
    # ^ (ts, lat, lon, point_risk_0_1)
    inside_geofences: List[str] = field(default_factory=list)
    last_progress_at: datetime | None = None
    last_known_position_km: float = 0.0
    auto_sos_fired: bool = False
    user_sos_fired: bool = False
    arrived_at: datetime | None = None

    # ---- derived ----

    @property
    def distance_remaining_km(self) -> float:
        return max(0.0, self.plan.distance_km - self.km_travelled)

    @property
    def progress_pct(self) -> int:
        if self.plan.distance_km <= 0:
            return 100
        return int(round(min(100.0, 100.0 * self.km_travelled / self.plan.distance_km)))

    @property
    def eta_remaining_min(self) -> float:
        return (self.distance_remaining_km / max(1.0, AVG_TRAVEL_KMH)) * 60.0

    @property
    def expected_arrival(self) -> datetime | None:
        if self.last_tick_at is None:
            return None
        return self.last_tick_at + timedelta(minutes=self.eta_remaining_min)

    def position(self) -> Tuple[float, float] | None:
        if not self.plan.coords:
            return None
        return _interp_position(self.plan, self.km_travelled)


# ---------------------------------------------------------------- helpers


def _bucket(lat: float, lon: float) -> Tuple[float, float]:
    return (round(lat / LOCATION_BUCKET_DEG) * LOCATION_BUCKET_DEG,
            round(lon / LOCATION_BUCKET_DEG) * LOCATION_BUCKET_DEG)


def _make_plan(route, *, origin_label: str = "Start", dest_label: str = "Destination") -> TripPlan:
    """Snapshot a `RouteResult` into a `TripPlan` (with prefix-sum)."""
    coords = list(route.coords)
    cum = [0.0]
    for (la, lo), (lb, lob) in zip(coords, coords[1:]):
        cum.append(cum[-1] + haversine_km(la, lo, lb, lob))
    return TripPlan(
        route_mode=route.mode,
        coords=coords,
        cum_km=cum,
        distance_km=float(route.distance_km),
        eta_minutes=float(route.eta_minutes),
        avg_safety=int(route.avg_safety),
        min_safety=int(route.min_safety),
        notes=list(route.notes),
        origin_label=origin_label,
        dest_label=dest_label,
        depart_at=getattr(route, "depart_at", None),
    )


def _interp_position(plan: TripPlan, km: float) -> Tuple[float, float]:
    """Interpolate (lat, lon) at `km` along the route prefix-sum."""
    coords = plan.coords
    cum = plan.cum_km
    if not coords:
        return (0.0, 0.0)
    if km <= 0.0 or len(coords) == 1:
        return coords[0]
    if km >= cum[-1]:
        return coords[-1]
    # binary search
    lo, hi = 0, len(cum) - 1
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if cum[mid] <= km:
            lo = mid
        else:
            hi = mid
    seg_len = max(1e-9, cum[hi] - cum[lo])
    f = (km - cum[lo]) / seg_len
    la, lo_a = coords[lo]
    lb, lo_b = coords[hi]
    return (la + (lb - la) * f, lo_a + (lo_b - lo_a) * f)


def _scan_ahead(
    plan: TripPlan, km: float, lookahead_km: float, n: int = 16,
) -> List[Tuple[float, Tuple[float, float]]]:
    """Sample `n` positions ahead of `km` up to `km + lookahead_km`.

    Returns `[(km_offset, (lat, lon)), ...]` so callers can label distances.
    """
    end = min(plan.cum_km[-1] if plan.cum_km else km, km + lookahead_km)
    if end <= km:
        return []
    step = (end - km) / max(1, n)
    return [(k - km, _interp_position(plan, k))
            for k in (km + step * i for i in range(1, n + 1))]


def _dominant_category_at(
    lat: float, lon: float, incidents: Sequence[Mapping],
    *, radius_km: float = 1.5,
) -> str | None:
    """Heaviest-severity category among recent-ish nearby incidents."""
    best_cat: str | None = None
    best_score = 0.0
    for r in incidents:
        try:
            ilat = float(r.get("lat")); ilon = float(r.get("lon"))
        except (TypeError, ValueError):
            continue
        d = haversine_km(lat, lon, ilat, ilon)
        if d > radius_km:
            continue
        cat = str(r.get("category", "other")).lower()
        sev = CATEGORY_SEVERITY.get(cat, 2)
        # closer + heavier wins; verified gets a small bump
        verified = 1.4 if str(r.get("status")) == "verified" else 1.0
        score = sev * verified * (1.0 - d / radius_km)
        if score > best_score:
            best_score = score
            best_cat = cat
    return best_cat


def _geofences_at(lat: float, lon: float, geofences: Mapping) -> List[str]:
    names: List[str] = []
    for feat in geofences.get("features", []) if geofences else []:
        try:
            poly = feat["geometry"]["coordinates"][0]
        except (KeyError, IndexError):
            continue
        if point_in_polygon(lat, lon, poly):
            names.append(feat.get("properties", {}).get("name", "risk zone"))
    return names


def _nearest_help_poi(
    lat: float, lon: float, pois: Sequence[Mapping], *, max_km: float = 4.0,
) -> Tuple[str, float] | None:
    best: Tuple[str, float] | None = None
    for poi in pois:
        try:
            ptype = str(poi.get("ptype", "")).lower()
            if ptype not in HELP_POI_TYPES:
                continue
            plat = float(poi.get("lat")); plon = float(poi.get("lon"))
        except (TypeError, ValueError):
            continue
        d = haversine_km(lat, lon, plat, plon)
        if d > max_km:
            continue
        if best is None or d < best[1]:
            best = (str(poi.get("name", ptype.title())), d)
    return best


# ---------------------------------------------------------------- engine


def start_trip(
    route, *, origin_label: str = "Start", dest_label: str = "Destination",
    speed_factor: float = 4.0, now: datetime | None = None,
) -> TripSession:
    """Snapshot a planned route and open a fresh active trip."""
    now = now or datetime.utcnow()
    plan = _make_plan(route, origin_label=origin_label, dest_label=dest_label)
    trip = TripSession(
        trip_id=uuid.uuid4().hex[:12],
        plan=plan,
        started_at=now,
        speed_factor=max(0.25, float(speed_factor)),
        last_tick_at=now,
        last_progress_at=now,
    )
    trip.milestones.append(Milestone(
        ts=now, kind="departure",
        summary=f"Departed {origin_label} → {dest_label}",
        payload={"route_mode": plan.route_mode,
                 "distance_km": plan.distance_km,
                 "expected_min": plan.eta_minutes},
    ))
    trip.alerts.append(Alert(
        id=uuid.uuid4().hex[:8], ts=now, kind="departure", severity="info",
        message=f"Trip started · {plan.route_mode} route · {plan.distance_km:g} km, ETA {plan.eta_minutes:g} min",
        location=plan.coords[0] if plan.coords else None,
        payload={"route_mode": plan.route_mode},
    ))
    return trip


def _recent_alert(
    trip: TripSession, kind: str, bucket: Tuple[float, float] | None, now: datetime,
) -> bool:
    """True iff an alert with the same kind/bucket fired inside the cooldown."""
    horizon = now - timedelta(seconds=ALERT_COOLDOWN_S)
    for a in reversed(trip.alerts):
        if a.ts < horizon:
            return False
        if a.kind != kind:
            continue
        if bucket is None and a.location is None:
            return True
        if a.location is None:
            continue
        if _bucket(*a.location) == bucket:
            return True
    return False


def _push_alert(trip: TripSession, **kw) -> Alert:
    a = Alert(id=uuid.uuid4().hex[:8], **kw)
    trip.alerts.append(a)
    return a


def tick(
    trip: TripSession,
    *,
    incidents: Sequence[Mapping],
    geofences: Mapping,
    pois: Sequence[Mapping],
    forecaster=None,
    now: datetime | None = None,
) -> List[Alert]:
    """Advance the simulated journey by elapsed wall-clock time.

    Returns the list of *new* alerts fired this tick (already appended to
    `trip.alerts`). The caller can fan them out to trusted contacts via
    `dispatch_broadcasts`.
    """
    now = now or datetime.utcnow()
    new_alerts: List[Alert] = []

    if trip.status != "active":
        trip.last_tick_at = now
        return new_alerts

    # ---- advance position
    last = trip.last_tick_at or trip.started_at
    dt_h = max(0.0, (now - last).total_seconds() / 3600.0)
    advance_km = dt_h * AVG_TRAVEL_KMH * trip.speed_factor
    if advance_km > 0:
        before = trip.km_travelled
        trip.km_travelled = min(trip.plan.distance_km, before + advance_km)
        if trip.km_travelled - before > 0.005:
            trip.last_progress_at = now
            trip.last_known_position_km = trip.km_travelled

    pos = trip.position() or (0.0, 0.0)
    lat, lon = pos
    here_risk = point_risk(lat, lon, incidents, geofences, pois, now=now)
    trip.heartbeats.append((now, lat, lon, here_risk))
    if len(trip.heartbeats) > HEARTBEAT_KEEP:
        trip.heartbeats = trip.heartbeats[-HEARTBEAT_KEEP:]

    # ---- arrival
    if trip.km_travelled >= trip.plan.distance_km - 1e-6 and trip.status == "active":
        trip.status = "completed"
        trip.arrived_at = now
        trip.milestones.append(Milestone(
            ts=now, kind="arrival",
            summary=f"Arrived at {trip.plan.dest_label}",
            payload={"travel_min": (now - trip.started_at).total_seconds() / 60.0},
        ))
        a = _push_alert(
            trip, ts=now, kind="arrival", severity="info",
            message=f"Arrived at {trip.plan.dest_label} — safe trip!",
            location=pos,
        )
        new_alerts.append(a)
        trip.last_tick_at = now
        return new_alerts

    # ---- geofence transitions
    inside_now = _geofences_at(lat, lon, geofences)
    entered = [n for n in inside_now if n not in trip.inside_geofences]
    exited = [n for n in trip.inside_geofences if n not in inside_now]
    if entered:
        for name in entered:
            a = _push_alert(
                trip, ts=now, kind="geofence_enter", severity="warn",
                message=f"Entering geofenced risk zone · {name}",
                location=pos, payload={"zone": name},
            )
            trip.milestones.append(Milestone(
                ts=now, kind="geofence_enter",
                summary=f"Entered geofence: {name}",
                payload={"zone": name},
            ))
            new_alerts.append(a)
    if exited:
        for name in exited:
            a = _push_alert(
                trip, ts=now, kind="geofence_exit", severity="info",
                message=f"Cleared {name} — back to safer ground",
                location=pos, payload={"zone": name},
            )
            trip.milestones.append(Milestone(
                ts=now, kind="geofence_exit",
                summary=f"Exited geofence: {name}",
                payload={"zone": name},
            ))
            new_alerts.append(a)
    trip.inside_geofences = inside_now

    # ---- look-ahead risk scan
    samples = _scan_ahead(trip.plan, trip.km_travelled, LOOKAHEAD_KM, n=12)
    peak_dk: float | None = None
    peak_pt: Tuple[float, float] | None = None
    peak_risk: float = 0.0
    for dk, (slat, slon) in samples:
        r = point_risk(slat, slon, incidents, geofences, pois, now=now)
        if r > peak_risk:
            peak_risk = r
            peak_dk = dk
            peak_pt = (slat, slon)

    if peak_pt is not None and peak_risk >= RISK_AHEAD_THRESHOLD:
        bucket = _bucket(*peak_pt)
        if not _recent_alert(trip, "risk_ahead", bucket, now):
            cat = _dominant_category_at(*peak_pt, incidents=incidents)
            cat_phrase = f" · {cat}" if cat else ""
            sev = "critical" if peak_risk >= 0.7 else "warn"
            a = _push_alert(
                trip, ts=now, kind="risk_ahead", severity=sev,
                message=f"High-risk segment in {peak_dk*1000:.0f} m{cat_phrase}",
                location=peak_pt, lookahead_km=peak_dk,
                payload={"risk": peak_risk, "category": cat},
            )
            new_alerts.append(a)

    # ---- safer-segment-coming-up after a sustained warn streak
    if (trip.alerts and trip.alerts[-1].kind == "risk_ahead"
            and peak_risk <= RISK_RECOVERY_THRESHOLD and samples):
        # last risk_ahead within 60s suggests we've cleared it
        last_warn = next((a for a in reversed(trip.alerts)
                          if a.kind == "risk_ahead"), None)
        if last_warn and (now - last_warn.ts).total_seconds() <= 90:
            ahead_pt = samples[min(2, len(samples) - 1)][1]
            bucket = _bucket(*ahead_pt)
            if not _recent_alert(trip, "safer_segment", bucket, now):
                a = _push_alert(
                    trip, ts=now, kind="safer_segment", severity="info",
                    message="Risk corridor cleared — safer stretch ahead",
                    location=ahead_pt,
                )
                new_alerts.append(a)

    # ---- stall / auto-SOS
    last_progress = trip.last_progress_at or trip.started_at
    stall_min = (now - last_progress).total_seconds() / 60.0
    in_red = (peak_risk >= RISK_AHEAD_THRESHOLD) or (here_risk >= RISK_AHEAD_THRESHOLD) or bool(inside_now)
    if (stall_min >= STALL_AUTO_SOS_MIN and in_red
            and not trip.auto_sos_fired and trip.status == "active"):
        trip.auto_sos_fired = True
        a = _push_alert(
            trip, ts=now, kind="auto_sos", severity="critical",
            message=f"Auto-SOS · stalled {stall_min:.0f} min in elevated-risk zone",
            location=pos,
            payload={"stall_min": stall_min, "risk": here_risk,
                     "geofences": inside_now},
        )
        trip.milestones.append(Milestone(
            ts=now, kind="auto_sos",
            summary=f"Auto-SOS dispatched after {stall_min:.0f} min stalled",
            payload={"stall_min": stall_min},
        ))
        new_alerts.append(a)
        nearest = _nearest_help_poi(lat, lon, pois)
        if nearest:
            a2 = _push_alert(
                trip, ts=now, kind="info", severity="info",
                message=f"Nearest help: {nearest[0]} · {nearest[1]:.1f} km",
                location=pos, payload={"poi": nearest[0]},
            )
            new_alerts.append(a2)

    trip.last_tick_at = now
    return new_alerts


def trigger_user_sos(trip: TripSession, *, now: datetime | None = None) -> Alert:
    """User-initiated SOS — surfaced to alerts/milestones/broadcasts."""
    now = now or datetime.utcnow()
    pos = trip.position()
    trip.user_sos_fired = True
    a = _push_alert(
        trip, ts=now, kind="auto_sos", severity="critical",
        message="Manual SOS — broadcasting position to trusted contacts",
        location=pos, payload={"manual": True},
    )
    trip.milestones.append(Milestone(
        ts=now, kind="auto_sos",
        summary="Manual SOS triggered",
        payload={"manual": True},
    ))
    return a


def pause_trip(trip: TripSession, *, now: datetime | None = None) -> None:
    if trip.status == "active":
        trip.status = "paused"
        trip.last_tick_at = now or datetime.utcnow()


def resume_trip(trip: TripSession, *, now: datetime | None = None) -> None:
    if trip.status == "paused":
        trip.status = "active"
        n = now or datetime.utcnow()
        trip.last_tick_at = n
        trip.last_progress_at = n


def cancel_trip(trip: TripSession, *, now: datetime | None = None) -> None:
    if trip.status in ("active", "paused"):
        trip.status = "cancelled"
        trip.last_tick_at = now or datetime.utcnow()


# ---------------------------------------------------------------- contacts + broadcasts


def load_contacts(path: Path) -> List[TrustedContact]:
    if not path.exists():
        return []
    out: List[TrustedContact] = []
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            try:
                out.append(TrustedContact.from_row(row))
            except Exception:
                continue
    return out


def save_contacts(contacts: Sequence[TrustedContact], path: Path) -> None:
    fieldnames = ["id", "name", "contact", "relationship", "opt_in"]
    rows = [
        {
            "id": c.id, "name": c.name, "contact": c.contact,
            "relationship": c.relationship,
            "opt_in": ",".join(c.opt_in),
        }
        for c in contacts
    ]
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def render_broadcast_body(
    alert: Alert, trip: TripSession, contact: TrustedContact,
) -> str:
    """Compose the simulated SMS/notification body for `alert → contact`."""
    pos = alert.location or trip.position() or (0.0, 0.0)
    maps = f"https://maps.google.com/?q={pos[0]:.5f},{pos[1]:.5f}"
    name_first = (contact.name.split() or ["friend"])[0]
    head = "WaySafe"
    if alert.kind == "departure":
        return (f"{head} · {name_first}, your contact left {trip.plan.origin_label} for "
                f"{trip.plan.dest_label}. Live at {maps}. ETA "
                f"{trip.plan.eta_minutes:.0f} min.")
    if alert.kind == "arrival":
        return (f"{head} · {name_first}, your contact has arrived safely at "
                f"{trip.plan.dest_label}.")
    if alert.kind == "auto_sos":
        return (f"{head} SOS · {name_first}, your contact may need help. "
                f"Last known position {pos[0]:.5f},{pos[1]:.5f} ({maps}).")
    if alert.kind in ("geofence_enter", "risk_ahead"):
        return (f"{head} alert · {alert.message}. Live at {maps}.")
    return f"{head} · {alert.message} ({maps})."


def dispatch_broadcasts(
    alert: Alert, trip: TripSession, contacts: Sequence[TrustedContact],
    *, log_path: Path | None = None,
) -> List[Broadcast]:
    """Fan an alert out to opted-in trusted contacts. Persists if `log_path`."""
    fanout: List[Broadcast] = []
    kind = alert.kind
    for c in contacts:
        if kind not in c.opt_in and not (kind == "info" and "info" in c.opt_in):
            continue
        b = Broadcast(
            id=uuid.uuid4().hex[:10], ts=alert.ts, trip_id=trip.trip_id,
            contact_id=c.id, contact_name=c.name, contact=c.contact,
            kind=kind, body=render_broadcast_body(alert, trip, c),
        )
        fanout.append(b)
    if log_path is not None and fanout:
        _append_broadcasts_csv(log_path, fanout)
    return fanout


def _append_broadcasts_csv(path: Path, rows: Iterable[Broadcast]) -> None:
    fieldnames = ["id", "ts", "trip_id", "contact_id", "contact_name",
                  "contact", "kind", "body"]
    new_file = not path.exists()
    with path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if new_file:
            w.writeheader()
        for b in rows:
            w.writerow(b.to_row())


# ---------------------------------------------------------------- digests + export


def trip_digest(trip: TripSession) -> dict:
    """Compact JSON-friendly summary used by the Trip Report tab."""
    counts: dict = {}
    for a in trip.alerts:
        counts[a.kind] = counts.get(a.kind, 0) + 1
    return {
        "trip_id": trip.trip_id,
        "status": trip.status,
        "started_at": trip.started_at.isoformat(timespec="seconds"),
        "completed_at": trip.arrived_at.isoformat(timespec="seconds")
        if trip.arrived_at else None,
        "origin": trip.plan.origin_label,
        "destination": trip.plan.dest_label,
        "route_mode": trip.plan.route_mode,
        "distance_km": trip.plan.distance_km,
        "km_travelled": round(trip.km_travelled, 2),
        "progress_pct": trip.progress_pct,
        "avg_safety": trip.plan.avg_safety,
        "alerts_total": len(trip.alerts),
        "alerts_by_kind": counts,
        "milestones": [
            {"ts": m.ts.isoformat(timespec="seconds"),
             "kind": m.kind, "summary": m.summary}
            for m in trip.milestones
        ],
        "auto_sos_fired": trip.auto_sos_fired,
        "user_sos_fired": trip.user_sos_fired,
    }


__all__ = [
    "Alert", "Milestone", "TripPlan", "TripSession",
    "TrustedContact", "Broadcast",
    "start_trip", "tick", "pause_trip", "resume_trip", "cancel_trip",
    "trigger_user_sos",
    "load_contacts", "save_contacts",
    "dispatch_broadcasts", "render_broadcast_body",
    "trip_digest",
    "AVG_TRAVEL_KMH", "LOOKAHEAD_KM", "RISK_AHEAD_THRESHOLD",
    "STALL_AUTO_SOS_MIN",
]
