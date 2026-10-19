import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pipeline import load, report, transform

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def con(tmp_path):
    c = load.connect(tmp_path / "test.db")
    yield c
    c.close()


def test_upsert_is_idempotent(con):
    rows = transform.carbon_rows(json.loads((FIX / "carbon.json").read_text()))
    assert load.upsert(con, "carbon_intensity", rows, ("period_start",)) == len(rows)
    assert load.upsert(con, "carbon_intensity", rows, ("period_start",)) == 0       # re-run adds nothing
    assert con.execute("SELECT count(*) FROM carbon_intensity").fetchone()[0] == len(rows)


def test_upsert_updates_revised_values(con):
    rows = transform.carbon_rows(json.loads((FIX / "carbon.json").read_text()))
    load.upsert(con, "carbon_intensity", rows, ("period_start",))
    rows[0]["intensity_gco2_kwh"] = 123
    load.upsert(con, "carbon_intensity", rows[:1], ("period_start",))
    got = con.execute("SELECT intensity_gco2_kwh FROM carbon_intensity WHERE period_start = ?",
                      (rows[0]["period_start"],)).fetchone()[0]
    assert got == 123


def test_export_csv(con, tmp_path):
    rows = transform.tfl_rows(json.loads((FIX / "tfl.json").read_text()), datetime(2026, 10, 19, tzinfo=timezone.utc))
    load.upsert(con, "tfl_line_status", rows, ("snapshot_at", "line_id"))
    load.export_csv(con, tmp_path / "out")
    lines = (tmp_path / "out" / "tfl_line_status.csv").read_text().strip().splitlines()
    assert len(lines) == len(rows) + 1


def test_readme_section_replaced_only_between_markers():
    text = f"intro\n{report.START}\nold\n{report.END}\noutro"
    new = report.update_readme(text, f"{report.START}\nnew\n{report.END}")
    assert new == f"intro\n{report.START}\nnew\n{report.END}\noutro"
    with pytest.raises(ValueError):
        report.update_readme("no markers", "x")


def test_badge_colour():
    b = report.badge({"carbon_latest": 162, "carbon_index": "moderate"})
    assert b == {"schemaVersion": 1, "label": "London grid now", "message": "162 gCO2/kWh (moderate)", "color": "yellow"}
