"""
Run the pipeline end to end: extract -> transform -> load -> export -> report.

    python -m pipeline.run                 # daily run: last 2 days of carbon and air data + a TfL snapshot
    python -m pipeline.run --days 14       # backfill up to 14 days
    python -m pipeline.run --no-report     # load data only

Each source is independent: if one API is down the others still load, the run is logged as 'partial',
and the exit code is non-zero only if every source failed.
"""
import argparse
import logging
import sys
from datetime import datetime, timezone

from . import config, extract, load, report, transform

log = logging.getLogger("pipeline")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--days", type=int, default=2, help="lookback window in days for carbon and air data (max 14)")
    ap.add_argument("--no-report", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    run_at = datetime.now(timezone.utc)
    con = load.connect(config.DB_PATH)
    counts, errors = {}, []
    jobs = [
        ("carbon", lambda: transform.carbon_rows(extract.fetch_carbon(args.days)), "carbon_intensity", ("period_start",)),
        ("air", lambda: transform.air_rows(extract.fetch_air_quality(args.days)), "air_quality", ("hour",)),
        ("tfl", lambda: transform.tfl_rows(extract.fetch_tfl_status(), run_at), "tfl_line_status", ("snapshot_at", "line_id")),
    ]
    for name, fetch, table, key in jobs:
        try:
            rows = fetch()
            new = load.upsert(con, table, rows, key)
            counts[name] = len(rows)
            log.info("%-6s fetched %4d rows, %4d new", name, len(rows), new)
        except Exception as exc:  # keep going: one failing API should not stop the others
            counts[name] = 0
            errors.append(f"{name}: {exc}")
            log.error("%s failed: %s", name, exc)

    status = "ok" if not errors else ("failed" if len(errors) == len(jobs) else "partial")
    con.execute("INSERT OR REPLACE INTO pipeline_runs VALUES (?, ?, ?, ?, ?, ?)",
                (run_at.strftime("%Y-%m-%dT%H:%M:%SZ"), counts["carbon"], counts["air"], counts["tfl"], status,
                 "; ".join(errors) or None))
    con.commit()
    load.export_csv(con, config.EXPORT_DIR)
    if not args.no_report and status != "failed":
        s = report.build(con)
        log.info("report updated: carbon now %s gCO2/kWh (%s)", s["carbon_latest"], s["carbon_index"])
    con.close()
    log.info("run %s", status)
    return 1 if status == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
