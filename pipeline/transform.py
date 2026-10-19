"""Transform: turn raw API JSON into validated, tidy rows (lists of dicts)."""
from datetime import datetime, timezone

FUELS = ["biomass", "coal", "imports", "gas", "nuclear", "other", "hydro", "solar", "wind"]


class ValidationError(ValueError):
    pass


def _iso(ts: str) -> str:
    """Normalise '2026-10-19T04:00Z' or '2026-10-19T04:00' (UTC) to '2026-10-19T04:00:00Z'."""
    ts = ts.rstrip("Z")
    return datetime.fromisoformat(ts).replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def carbon_rows(payload: dict) -> list[dict]:
    """One row per half hour: forecast intensity (gCO2/kWh), index band and % generation by fuel."""
    block = payload.get("data")
    if isinstance(block, list):          # /regional/regionid/13 shape
        block = block[0]
    periods = (block or {}).get("data")
    if not periods:
        raise ValidationError("carbon payload has no periods")
    rows = []
    for p in periods:
        intensity = p["intensity"]["forecast"]
        if intensity is None or not 0 <= intensity <= 1000:
            raise ValidationError(f"implausible carbon intensity {intensity} at {p['from']}")
        mix = {m["fuel"]: float(m["perc"]) for m in p.get("generationmix", [])}
        total = sum(mix.values())
        if mix and not 95 <= total <= 105:
            raise ValidationError(f"generation mix sums to {total:.1f}% at {p['from']}")
        row = {"period_start": _iso(p["from"]), "period_end": _iso(p["to"]),
               "intensity_gco2_kwh": int(intensity), "intensity_index": p["intensity"]["index"]}
        row.update({f"pct_{f}": mix.get(f, 0.0) for f in FUELS})
        rows.append(row)
    return rows


def air_rows(payload: dict, now: datetime | None = None) -> list[dict]:
    """One row per hour up to now (future forecast hours are dropped). Missing values stay None."""
    now = now or datetime.now(timezone.utc)
    h = payload.get("hourly")
    if not h or "time" not in h:
        raise ValidationError("air quality payload has no hourly block")
    rows = []
    for i, t in enumerate(h["time"]):
        ts = _iso(t)
        if ts > now.strftime("%Y-%m-%dT%H:%M:%SZ"):
            continue
        row = {"hour": ts}
        for var in ["pm10", "pm2_5", "nitrogen_dioxide", "ozone", "european_aqi"]:
            v = h.get(var, [None] * len(h["time"]))[i]
            if v is not None and v < 0:
                raise ValidationError(f"negative {var} at {ts}")
            row[var] = v
        if any(row[v] is not None for v in ["pm10", "pm2_5", "nitrogen_dioxide", "ozone"]):
            rows.append(row)
    return rows


def tfl_rows(payload: list, snapshot_at: datetime | None = None) -> list[dict]:
    """One row per line for this snapshot, keeping the worst (lowest severity number) status."""
    snapshot_at = snapshot_at or datetime.now(timezone.utc)
    snap = snapshot_at.replace(second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not isinstance(payload, list) or not payload:
        raise ValidationError("TfL payload is empty")
    rows = []
    for line in payload:
        statuses = line.get("lineStatuses") or []
        if not statuses:
            continue
        worst = min(statuses, key=lambda s: s.get("statusSeverity", 10))
        rows.append({"snapshot_at": snap, "line_id": line["id"], "line_name": line["name"], "mode": line["modeName"],
                     "status_severity": int(worst.get("statusSeverity", 10)),
                     "status": worst.get("statusSeverityDescription", "Unknown"),
                     "reason": (worst.get("reason") or "").strip()[:500] or None})
    return rows
