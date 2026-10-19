"""
Print summary statistics for everything collected so far (used for the 'Findings' section of the README).

    python -m pipeline.insights
"""
import sqlite3

import pandas as pd

from . import config


def main() -> None:
    con = sqlite3.connect(config.DB_PATH)
    c = pd.read_sql("SELECT * FROM carbon_intensity", con, parse_dates=["period_start"])
    a = pd.read_sql("SELECT * FROM air_quality", con, parse_dates=["hour"])
    t = pd.read_sql("SELECT * FROM tfl_line_status", con)
    print(f"Carbon: {len(c)} half-hours, {c.period_start.min()} to {c.period_start.max()}")
    print(f"  mean {c.intensity_gco2_kwh.mean():.1f}, min {c.intensity_gco2_kwh.min()}, max {c.intensity_gco2_kwh.max()} gCO2/kWh")
    print(f"  correlation with wind share {c[['intensity_gco2_kwh', 'pct_wind']].corr().iloc[0, 1]:.3f}, "
          f"with gas share {c[['intensity_gco2_kwh', 'pct_gas']].corr().iloc[0, 1]:.3f}")
    windy = c.pct_wind >= 40
    print(f"  mean when wind >= 40%: {c[windy].intensity_gco2_kwh.mean():.1f} ({windy.sum()} half-hours); "
          f"otherwise {c[~windy].intensity_gco2_kwh.mean():.1f} ({(~windy).sum()})")
    print("  index bands:", c.intensity_index.value_counts().to_dict())
    hourly = c.groupby(c.period_start.dt.hour).intensity_gco2_kwh.mean()
    print(f"  cleanest hour of day (UTC) {hourly.idxmin()}:00 ({hourly.min():.1f}), dirtiest {hourly.idxmax()}:00 ({hourly.max():.1f})")
    print(f"Air: {len(a)} hours, {a.hour.min()} to {a.hour.max()}")
    print(f"  NO2 mean {a.nitrogen_dioxide.mean():.1f}, max {a.nitrogen_dioxide.max()} at {a.loc[a.nitrogen_dioxide.idxmax(), 'hour']}")
    daily = a.groupby(a.hour.dt.date).agg(no2=("nitrogen_dioxide", "mean"), n=("nitrogen_dioxide", "size"))
    full = daily[daily.n == 24]
    print(f"  full days with daily-mean NO2 above the WHO 24h guideline (25): {(full.no2 > 25).sum()} of {len(full)}")
    by_h = a.groupby(a.hour.dt.hour).nitrogen_dioxide.mean()
    print(f"  highest NO2 hour of day (UTC): {by_h.idxmax()}:00 ({by_h.max():.1f}); lowest {by_h.idxmin()}:00 ({by_h.min():.1f})")
    print(f"TfL: {t.snapshot_at.nunique()} snapshots, {len(t)} line-status rows; "
          f"good service share {(t.status == 'Good Service').mean():.1%}")


if __name__ == "__main__":
    main()
