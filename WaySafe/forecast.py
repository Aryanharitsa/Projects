"""Spatiotemporal hazard forecaster for WaySafe.

Pure-Python, zero-dep predictor that learns where and *when* hazards tend
to happen and exposes a 0..1 forecast risk for any (lat, lon, datetime).

The model
---------
- Snap the city to a regular ~`cell_km` square grid.
- For every historical incident, accumulate a weight
      w = severity × verified_bump × recency_decay(t)
  into the (cell, day-of-week, hour) bucket. Recency decays with a
  configurable half-life in days so older patterns fade.
- Each bucket's expected weighted count uses an **Empirical-Bayes**
  posterior mean against a global per-bucket prior (so sparse cells
  shrink toward the city-wide average for that hour-of-day):

      λ̂(c, t) = (k_{c,t} + α · π_t) / (1 + α)

  where π_t = Σ_c k_{c,t} / N_cells (the per-cell prior at time t)
  and α is the pseudo-count strength.
- Risk in [0, 1] uses Poisson saturation:

      risk = 1 − exp(−κ · λ̂)

  κ is calibrated so the highest-density historical buckets land near
  ~0.85 risk and a quiet street stays around ~0.05.
- Top-category forecast is a cell-conditional mix smoothed toward the
  global category prior so quiet cells still get sensible guesses.

API
---
- `HazardForecaster(incidents, ...)` — fit on construction.
  - `risk_at(lat, lon, when) -> float`
  - `forecast(lat, lon, when) -> ForecastResult`  (risk + confidence + categories)
  - `risk_curve(lat, lon, day=date) -> List[float]`  (24 hourly values)
  - `risk_grid(when, bbox=None, n=36) -> List[(lat, lon, risk)]`  (HeatmapLayer)
  - `hotspots(when, k=5) -> List[dict]`
  - `find_best_window(lat, lon, around, span_h, step_min) -> List[(t, risk)]`
  - `summary() -> dict`
- Module helper `from_csv(path, ...)`
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from datetime import date as _date, datetime, timedelta
from typing import Iterable, List, Mapping, Sequence, Tuple

from safety import CATEGORY_SEVERITY


DEFAULT_CELL_KM = 0.5
DEFAULT_PSEUDO = 3.0
DEFAULT_KAPPA = 0.85
DEFAULT_HALF_LIFE_D = 14.0

# Triangular kernel that smooths observed/prior counts across the 3×3
# neighbourhood of (DOW, hour). One verified incident at (Sat, 22:00) bleeds
# softly into (Fri/Sun, 21:00–23:00) so the forecast surface is continuous.
_HOUR_KERNEL = ((-1, 0.45), (0, 1.0), (1, 0.45))
_DOW_KERNEL = ((-1, 0.35), (0, 1.0), (1, 0.35))
_KERNEL_MASS = sum(wh * wd for _, wh in _HOUR_KERNEL for _, wd in _DOW_KERNEL)


@dataclass
class ForecastResult:
    risk: float                         # 0..1
    expected_count: float               # posterior weighted count λ̂
    confidence: str                     # "low" | "medium" | "high"
    top_categories: List[Tuple[str, float]]
    bucket_obs: float                   # raw observed weight in this bucket
    cell_obs: float                     # total observed weight in this cell
    explain: List[str] = field(default_factory=list)


def _parse_ts(s) -> datetime | None:
    if s is None:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "")).replace(tzinfo=None)
    except Exception:
        return None


class HazardForecaster:
    """Fit-on-construction. All methods are read-only after that."""

    def __init__(
        self,
        incidents: Iterable[Mapping],
        *,
        cell_km: float = DEFAULT_CELL_KM,
        pseudo_count: float = DEFAULT_PSEUDO,
        kappa: float = DEFAULT_KAPPA,
        half_life_days: float = DEFAULT_HALF_LIFE_D,
        now: datetime | None = None,
    ) -> None:
        self.cell_km = cell_km
        self.alpha = pseudo_count
        self.kappa = kappa
        self.half_life_days = half_life_days
        self.now = now or datetime.utcnow()
        self._fit(list(incidents))

    # ---------------- fit ----------------

    def _fit(self, rows_in: List[Mapping]) -> None:
        rows: List[Tuple[float, float, datetime, str, float]] = []
        lats: List[float] = []
        lons: List[float] = []
        for r in rows_in:
            try:
                lat = float(r.get("lat"))
                lon = float(r.get("lon"))
            except (TypeError, ValueError):
                continue
            ts = _parse_ts(r.get("created_at", ""))
            if ts is None:
                continue
            cat = str(r.get("category", "other")).lower()
            sev = CATEGORY_SEVERITY.get(cat, 2)
            verified = 1.4 if str(r.get("status")) == "verified" else 1.0
            age_days = max(0.0, (self.now - ts).total_seconds() / 86400.0)
            recency = 0.5 ** (age_days / max(0.5, self.half_life_days))
            rows.append((lat, lon, ts, cat, sev * verified * recency))
            lats.append(lat)
            lons.append(lon)

        if rows:
            self.center_lat = sum(lats) / len(lats)
            self.center_lon = sum(lons) / len(lons)
        else:
            self.center_lat, self.center_lon = 15.5, 73.83

        self.lat_step = self.cell_km / 111.0
        self.lon_step = self.cell_km / (
            111.0 * max(0.2, math.cos(math.radians(self.center_lat)))
        )

        cells: dict[Tuple[int, int], dict] = {}
        bucket_totals: dict[Tuple[int, int], float] = {}
        cat_globals: dict[str, float] = {}
        global_total = 0.0
        n_rows = 0

        for lat, lon, ts, cat, w in rows:
            cell = self._cell(lat, lon)
            dow, hour = ts.weekday(), ts.hour
            c = cells.setdefault(
                cell,
                {
                    "lat": (cell[0] + 0.5) * self.lat_step,
                    "lon": (cell[1] + 0.5) * self.lon_step,
                    "counts": {},        # (dow, hour) -> weight
                    "cat_counts": {},    # (dow, hour, cat) -> weight
                    "total": 0.0,
                    "n_raw": 0,
                },
            )
            c["counts"][(dow, hour)] = c["counts"].get((dow, hour), 0.0) + w
            c["cat_counts"][(dow, hour, cat)] = c["cat_counts"].get((dow, hour, cat), 0.0) + w
            c["total"] += w
            c["n_raw"] += 1
            bucket_totals[(dow, hour)] = bucket_totals.get((dow, hour), 0.0) + w
            cat_globals[cat] = cat_globals.get(cat, 0.0) + w
            global_total += w
            n_rows += 1

        self.cells = cells
        self.bucket_totals = bucket_totals
        self.global_total = global_total
        self.cat_globals = cat_globals
        self.n_rows = n_rows
        self.n_cells_seen = max(1, len(cells))

    # ---------------- cell math ----------------

    def _cell(self, lat: float, lon: float) -> Tuple[int, int]:
        return (
            int(math.floor(lat / self.lat_step)),
            int(math.floor(lon / self.lon_step)),
        )

    def _cell_center(self, cell: Tuple[int, int]) -> Tuple[float, float]:
        return (
            (cell[0] + 0.5) * self.lat_step,
            (cell[1] + 0.5) * self.lon_step,
        )

    # ---------------- posterior ----------------

    def _lambda(
        self, cell: Tuple[int, int], dow: int, hour: int
    ) -> Tuple[float, float, float, float]:
        c = self.cells.get(cell)
        kernel_obs = 0.0
        kernel_prior = 0.0
        for dh, wh in _HOUR_KERNEL:
            h = (hour + dh) % 24
            for dd, wd in _DOW_KERNEL:
                d = (dow + dd) % 7
                k = wh * wd
                if c is not None:
                    kernel_obs += k * c["counts"].get((d, h), 0.0)
                kernel_prior += k * (
                    self.bucket_totals.get((d, h), 0.0) / self.n_cells_seen
                )
        cell_total = c["total"] if c else 0.0
        lam = (kernel_obs + self.alpha * kernel_prior) / (_KERNEL_MASS + self.alpha)
        # `obs` reported back to callers is the raw at-bucket weight
        obs = c["counts"].get((dow, hour), 0.0) if c else 0.0
        return lam, kernel_prior / _KERNEL_MASS, obs, cell_total

    # ---------------- public API ----------------

    def risk_at(self, lat: float, lon: float, when: datetime | None = None) -> float:
        when = when or self.now
        cell = self._cell(lat, lon)
        lam, _, _, _ = self._lambda(cell, when.weekday(), when.hour)
        return 1.0 - math.exp(-self.kappa * lam)

    def forecast(
        self, lat: float, lon: float, when: datetime | None = None
    ) -> ForecastResult:
        when = when or self.now
        cell = self._cell(lat, lon)
        dow, hour = when.weekday(), when.hour
        lam, prior, obs, cell_total = self._lambda(cell, dow, hour)
        risk = 1.0 - math.exp(-self.kappa * lam)

        if obs >= 1.5:
            conf = "high"
        elif cell_total >= 1.5 or obs >= 0.5:
            conf = "medium"
        else:
            conf = "low"

        # Cell-conditional category mix, smoothed toward the global prior.
        cat_scores: dict[str, float] = {}
        c = self.cells.get(cell)
        global_total = max(1e-9, self.global_total)
        for cat, total in self.cat_globals.items():
            global_p = total / global_total
            if c is None:
                local_p = global_p
            else:
                local = c["cat_counts"].get((dow, hour, cat), 0.0)
                local_total = c["counts"].get((dow, hour), 0.0)
                local_p = (local + global_p) / (local_total + 1.0)
            cat_scores[cat] = local_p
        norm = sum(cat_scores.values()) or 1.0
        ordered = sorted(
            ((c, p / norm) for c, p in cat_scores.items()),
            key=lambda x: -x[1],
        )

        explain: List[str] = []
        if conf == "high":
            explain.append(f"This cell has seen incidents at this hour ({obs:.1f} weight).")
        elif conf == "medium":
            explain.append(
                f"Cell history is sparse at this hour — borrowed strength from "
                f"the {dow_name(dow)} {hour:02d}:00 city prior (π={prior:.2f})."
            )
        else:
            explain.append(
                f"No directly comparable history — falling back almost entirely "
                f"on the city-wide {dow_name(dow)} {hour:02d}:00 prior."
            )
        if 22 <= hour or hour < 5:
            explain.append("Late-night window — historical hazards skew higher here.")

        return ForecastResult(
            risk=risk,
            expected_count=lam,
            confidence=conf,
            top_categories=ordered[:3],
            bucket_obs=obs,
            cell_obs=cell_total,
            explain=explain,
        )

    def risk_curve(
        self, lat: float, lon: float, day: datetime | _date | int | None = None
    ) -> List[float]:
        """24 hourly risks at `(lat, lon)` for the given day."""
        if day is None:
            base = self.now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif isinstance(day, datetime):
            base = day.replace(hour=0, minute=0, second=0, microsecond=0)
        elif isinstance(day, _date):
            base = datetime(day.year, day.month, day.day)
        else:
            # int dow — synthesise a date with that weekday near `now`
            target = int(day) % 7
            base = self.now.replace(hour=0, minute=0, second=0, microsecond=0)
            base += timedelta(days=(target - base.weekday()) % 7)
        return [self.risk_at(lat, lon, when=base.replace(hour=h)) for h in range(24)]

    def risk_grid(
        self,
        when: datetime | None = None,
        bbox: Tuple[float, float, float, float] | None = None,
        n: int = 36,
    ) -> List[Tuple[float, float, float]]:
        """Lattice of (lat, lon, risk) points for a HeatmapLayer."""
        when = when or self.now
        if bbox is None:
            if not self.cells:
                lat_lo, lat_hi = self.center_lat - 0.05, self.center_lat + 0.05
                lon_lo, lon_hi = self.center_lon - 0.05, self.center_lon + 0.05
            else:
                ls = [c[0] * self.lat_step for c in self.cells.keys()]
                os = [c[1] * self.lon_step for c in self.cells.keys()]
                lat_lo, lat_hi = min(ls) - 0.02, max(ls) + 0.02
                lon_lo, lon_hi = min(os) - 0.02, max(os) + 0.02
        else:
            lat_lo, lon_lo, lat_hi, lon_hi = bbox
        out: List[Tuple[float, float, float]] = []
        for i in range(n + 1):
            la = lat_lo + (lat_hi - lat_lo) * i / n
            for j in range(n + 1):
                lo = lon_lo + (lon_hi - lon_lo) * j / n
                r = self.risk_at(la, lo, when=when)
                if r > 0.04:
                    out.append((la, lo, r))
        return out

    def hotspots(self, when: datetime | None = None, k: int = 5) -> List[dict]:
        """Top-k cells by forecast risk for the given datetime."""
        when = when or self.now
        out: List[dict] = []
        for cell, c in self.cells.items():
            la, lo = self._cell_center(cell)
            r = self.risk_at(la, lo, when=when)
            top_cat = self._top_cat(cell, when.weekday(), when.hour)
            out.append(
                {
                    "lat": la,
                    "lon": lo,
                    "risk": r,
                    "observed_weight": round(c["total"], 2),
                    "incidents": c["n_raw"],
                    "top_category": top_cat,
                }
            )
        out.sort(key=lambda x: -x["risk"])
        return out[:k]

    def _top_cat(self, cell: Tuple[int, int], dow: int, hour: int) -> str:
        c = self.cells.get(cell)
        if not c:
            if not self.cat_globals:
                return "other"
            return max(self.cat_globals.items(), key=lambda x: x[1])[0]
        sub = {k[2]: v for k, v in c["cat_counts"].items() if k[0] == dow and k[1] == hour}
        if not sub:
            sub = {}
            for k, v in c["cat_counts"].items():
                sub[k[2]] = sub.get(k[2], 0.0) + v
        if not sub:
            return "other"
        return max(sub.items(), key=lambda x: x[1])[0]

    def find_best_window(
        self,
        lat: float,
        lon: float,
        around: datetime | None = None,
        *,
        span_h: float = 4.0,
        step_min: int = 20,
    ) -> List[Tuple[datetime, float]]:
        """Search ±`span_h` around `around` for the time with the lowest forecast risk.

        Returns the full sweep sorted by risk ascending so callers can show
        a recommendation *and* the runner-up.
        """
        around = around or self.now
        steps = int(span_h * 60 / step_min)
        out: List[Tuple[datetime, float]] = []
        for k in range(-steps, steps + 1):
            t = around + timedelta(minutes=k * step_min)
            out.append((t, self.risk_at(lat, lon, when=t)))
        out.sort(key=lambda x: x[1])
        return out

    def summary(self) -> dict:
        bucket_by_hour: dict[int, float] = {}
        bucket_by_dow: dict[int, float] = {}
        for (dow, h), w in self.bucket_totals.items():
            bucket_by_hour[h] = bucket_by_hour.get(h, 0.0) + w
            bucket_by_dow[dow] = bucket_by_dow.get(dow, 0.0) + w
        return {
            "incidents_trained": self.n_rows,
            "cells": len(self.cells),
            "global_weight": round(self.global_total, 2),
            "peak_hour": (max(bucket_by_hour, key=bucket_by_hour.get) if bucket_by_hour else None),
            "peak_dow": (max(bucket_by_dow, key=bucket_by_dow.get) if bucket_by_dow else None),
            "top_categories": sorted(
                [(k, round(v, 2)) for k, v in self.cat_globals.items()],
                key=lambda x: -x[1],
            )[:3],
            "params": {
                "cell_km": self.cell_km,
                "pseudo_count": self.alpha,
                "kappa": self.kappa,
                "half_life_days": self.half_life_days,
            },
        }


# ---------------- helpers ----------------

_DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def dow_name(dow: int) -> str:
    return _DOW[dow % 7]


def from_csv(path: str, **kwargs) -> HazardForecaster:
    with open(path) as f:
        rows = list(csv.DictReader(f))
    return HazardForecaster(rows, **kwargs)
