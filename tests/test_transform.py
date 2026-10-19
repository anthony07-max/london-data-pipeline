"""Transform tests run against real API responses saved in tests/fixtures (captured 19 Oct 2026)."""
import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pipeline import transform

FIX = Path(__file__).parent / "fixtures"


def fixture(name):
    return json.loads((FIX / name).read_text())


def test_carbon_rows_parse_real_response():
    rows = transform.carbon_rows(fixture("carbon.json"))
    assert len(rows) == 7                                     # 23:30 to 03:00, half-hourly
    r = rows[0]
    assert r["period_start"] == "2026-10-17T23:30:00Z" and r["period_end"] == "2026-10-18T00:00:00Z"
    assert isinstance(r["intensity_gco2_kwh"], int)
    mix = sum(v for k, v in r.items() if k.startswith("pct_"))
    assert 95 <= mix <= 105


def test_carbon_rejects_implausible_values():
    bad = fixture("carbon.json")
    bad["data"]["data"][0]["intensity"]["forecast"] = 5000
    with pytest.raises(transform.ValidationError):
        transform.carbon_rows(bad)


def test_carbon_accepts_current_endpoint_shape():
    payload = fixture("carbon.json")
    wrapped = {"data": [payload["data"]]}                     # /regional/regionid/13 returns a list
    assert transform.carbon_rows(wrapped) == transform.carbon_rows(payload)


def test_air_rows_drop_future_hours():
    payload = fixture("air.json")
    now = datetime(2026, 10, 18, 11, 30, tzinfo=timezone.utc)
    rows = transform.air_rows(payload, now=now)
    assert [r["hour"] for r in rows][-1] == "2026-10-18T11:00:00Z"
    assert len(rows) == 12
    assert all(r["nitrogen_dioxide"] is None or r["nitrogen_dioxide"] >= 0 for r in rows)


def test_air_rejects_negative_concentration():
    payload = copy.deepcopy(fixture("air.json"))
    payload["hourly"]["pm2_5"][0] = -3
    with pytest.raises(transform.ValidationError):
        transform.air_rows(payload, now=datetime(2026, 10, 19, tzinfo=timezone.utc))


def test_tfl_rows_keep_worst_status():
    payload = fixture("tfl.json")
    payload[0]["lineStatuses"] = [{"statusSeverity": 10, "statusSeverityDescription": "Good Service"},
                                  {"statusSeverity": 6, "statusSeverityDescription": "Severe Delays", "reason": "signal failure"}]
    rows = transform.tfl_rows(payload, datetime(2026, 10, 19, 7, 30, 12, tzinfo=timezone.utc))
    assert len(rows) == len(payload)
    assert rows[0]["status"] == "Severe Delays" and rows[0]["reason"] == "signal failure"
    assert rows[0]["snapshot_at"] == "2026-10-19T07:30:00Z"
    assert {r["mode"] for r in rows} >= {"tube", "dlr"}
