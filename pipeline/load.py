"""Load: idempotent upserts into SQLite, plus CSV exports."""
import csv
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS carbon_intensity (
    period_start TEXT PRIMARY KEY,          -- UTC, half-hourly
    period_end TEXT NOT NULL,
    intensity_gco2_kwh INTEGER NOT NULL,
    intensity_index TEXT NOT NULL,
    pct_biomass REAL, pct_coal REAL, pct_imports REAL, pct_gas REAL, pct_nuclear REAL,
    pct_other REAL, pct_hydro REAL, pct_solar REAL, pct_wind REAL,
    loaded_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE TABLE IF NOT EXISTS air_quality (
    hour TEXT PRIMARY KEY,                  -- UTC, hourly
    pm10 REAL, pm2_5 REAL, nitrogen_dioxide REAL, ozone REAL, european_aqi REAL,
    loaded_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE TABLE IF NOT EXISTS tfl_line_status (
    snapshot_at TEXT NOT NULL,
    line_id TEXT NOT NULL,
    line_name TEXT, mode TEXT,
    status_severity INTEGER, status TEXT, reason TEXT,
    PRIMARY KEY (snapshot_at, line_id)
);
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_at TEXT PRIMARY KEY,
    carbon_rows INTEGER, air_rows INTEGER, tfl_rows INTEGER, status TEXT, message TEXT
);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con


def upsert(con: sqlite3.Connection, table: str, rows: list[dict], key: tuple[str, ...]) -> int:
    """Insert rows, replacing existing rows with the same key (so re-running a day is safe).
    Returns the number of rows that are new to the table."""
    if not rows:
        return 0
    cols = list(rows[0].keys())
    before = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c not in key)
    sql = (f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))}) "
           f"ON CONFLICT ({', '.join(key)}) DO " + (f"UPDATE SET {updates}" if updates else "NOTHING"))
    con.executemany(sql, [tuple(r[c] for c in cols) for r in rows])
    con.commit()
    return con.execute(f"SELECT count(*) FROM {table}").fetchone()[0] - before


def export_csv(con: sqlite3.Connection, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for table, order in [("carbon_intensity", "period_start"), ("air_quality", "hour"),
                         ("tfl_line_status", "snapshot_at, line_id"), ("pipeline_runs", "run_at")]:
        cur = con.execute(f"SELECT * FROM {table} ORDER BY {order}")
        cols = [d[0] for d in cur.description if d[0] != "loaded_at"]
        idx = [i for i, d in enumerate(cur.description) if d[0] != "loaded_at"]
        with open(out_dir / f"{table}.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for r in cur:
                w.writerow([r[i] for i in idx])
