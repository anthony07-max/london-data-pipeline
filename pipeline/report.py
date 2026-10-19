"""Report: regenerate the chart, the README 'latest data' section and a shields.io badge from the database."""
import json
import re
import sqlite3
from datetime import datetime, timezone

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from . import config  # noqa: E402

START, END = "<!-- LATEST:START -->", "<!-- LATEST:END -->"
BADGE_COLOURS = {"very low": "brightgreen", "low": "green", "moderate": "yellow", "high": "orange", "very high": "red"}
FUEL_COLOURS = {"wind": "#4c9be8", "nuclear": "#9b59b6", "gas": "#7f8c8d", "biomass": "#8d6e63", "imports": "#f1c40f",
                "solar": "#f39c12", "hydro": "#1abc9c", "coal": "#2c3e50", "other": "#bdc3c7"}


def load_frames(con: sqlite3.Connection):
    carbon = pd.read_sql("SELECT * FROM carbon_intensity ORDER BY period_start", con, parse_dates=["period_start"])
    air = pd.read_sql("SELECT * FROM air_quality ORDER BY hour", con, parse_dates=["hour"])
    tfl = pd.read_sql("SELECT * FROM tfl_line_status ORDER BY snapshot_at", con, parse_dates=["snapshot_at"])
    runs = pd.read_sql("SELECT * FROM pipeline_runs ORDER BY run_at", con)
    return carbon, air, tfl, runs


def make_chart(carbon: pd.DataFrame, air: pd.DataFrame, path) -> None:
    fig, axes = plt.subplots(3, 1, figsize=(12, 11), sharex=True)
    ax = axes[0]
    ax.plot(carbon["period_start"], carbon["intensity_gco2_kwh"], color="#1f4e79", lw=1.2)
    daily = carbon.set_index("period_start")["intensity_gco2_kwh"].resample("D").mean()
    ax.plot(daily.index + pd.Timedelta(hours=12), daily.values, "o--", color="#e07b39", lw=1, ms=4, label="daily mean")
    ax.set_ylabel("gCO2 / kWh")
    ax.set_title("London electricity carbon intensity (half-hourly, NESO regional forecast)")
    ax.legend(loc="upper right")

    ax = axes[1]
    fuels = [f for f in FUEL_COLOURS if f"pct_{f}" in carbon and carbon[f"pct_{f}"].sum() > 0]
    ax.stackplot(carbon["period_start"], *[carbon[f"pct_{f}"] for f in fuels], labels=fuels,
                 colors=[FUEL_COLOURS[f] for f in fuels], alpha=0.9)
    ax.set_ylim(0, 100)
    ax.set_ylabel("% of generation")
    ax.set_title("Generation mix supplying London")
    ax.legend(loc="upper left", ncol=len(fuels), fontsize=8, framealpha=0.9)

    ax = axes[2]
    ax.plot(air["hour"], air["nitrogen_dioxide"], color="#c0392b", lw=1.2, label="NO2")
    ax.plot(air["hour"], air["pm2_5"], color="#2c3e50", lw=1.2, label="PM2.5")
    ax.axhline(25, color="#c0392b", ls=":", lw=1)
    ax.text(air["hour"].max(), 26, "WHO 24h NO2 guideline (25)", fontsize=8, color="#c0392b", ha="right")
    ax.set_ylabel("micrograms / m3")
    ax.set_title("Central London air quality (hourly, Open-Meteo / CAMS model)")
    ax.legend(loc="upper right")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    for a in axes:
        a.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def summary(carbon, air, tfl, runs, now=None) -> dict:
    now = now or datetime.now(timezone.utc)
    last = carbon.iloc[-1]
    last7 = carbon[carbon["period_start"] > last["period_start"] - pd.Timedelta(days=7)]
    cleanest = last7.loc[last7["intensity_gco2_kwh"].idxmin()]
    dirtiest = last7.loc[last7["intensity_gco2_kwh"].idxmax()]
    air_last = air.dropna(subset=["nitrogen_dioxide"]).iloc[-1]
    air7 = air[air["hour"] > air_last["hour"] - pd.Timedelta(days=7)]
    by_hour = last7.groupby(last7["period_start"].dt.hour)["intensity_gco2_kwh"].mean()
    s = {
        "updated_utc": now.strftime("%Y-%m-%d %H:%M UTC"),
        "carbon_latest": int(last["intensity_gco2_kwh"]), "carbon_index": last["intensity_index"],
        "carbon_latest_at": last["period_start"].strftime("%d %b %H:%M UTC"),
        "carbon_7d_mean": round(float(last7["intensity_gco2_kwh"].mean()), 1),
        "cleanest": (int(cleanest["intensity_gco2_kwh"]), cleanest["period_start"].strftime("%a %d %b %H:%M")),
        "dirtiest": (int(dirtiest["intensity_gco2_kwh"]), dirtiest["period_start"].strftime("%a %d %b %H:%M")),
        "cleanest_hour_utc": int(by_hour.idxmin()), "dirtiest_hour_utc": int(by_hour.idxmax()),
        "wind_7d": round(float(last7["pct_wind"].mean()), 1), "gas_7d": round(float(last7["pct_gas"].mean()), 1),
        "no2_latest": air_last["nitrogen_dioxide"], "pm25_latest": air_last["pm2_5"],
        "air_latest_at": air_last["hour"].strftime("%d %b %H:%M UTC"),
        "no2_7d_mean": round(float(air7["nitrogen_dioxide"].mean()), 1),
        "pm25_7d_mean": round(float(air7["pm2_5"].mean()), 1),
        "carbon_rows": len(carbon), "air_rows": len(air), "tfl_snapshots": int(tfl["snapshot_at"].nunique()),
        "first_period": carbon["period_start"].min().strftime("%d %b %Y"), "runs": len(runs),
    }
    if len(tfl):
        latest_snap = tfl[tfl["snapshot_at"] == tfl["snapshot_at"].max()]
        s["tfl_latest_at"] = latest_snap["snapshot_at"].iloc[0].strftime("%d %b %H:%M UTC")
        s["tfl_lines"] = len(latest_snap)
        s["tfl_good"] = int((latest_snap["status"] == "Good Service").sum())
        s["tfl_issues"] = [f"{r.line_name}: {r.status}" for r in latest_snap.itertuples() if r.status != "Good Service"]
    return s


def render_section(s: dict) -> str:
    issues = ", ".join(s.get("tfl_issues", [])) or "none"
    return f"""{START}
_Last updated by the pipeline: **{s['updated_utc']}** · {s['runs']} runs · {s['carbon_rows']:,} half-hours of carbon data since {s['first_period']}, {s['air_rows']:,} hours of air quality, {s['tfl_snapshots']} TfL snapshots_

| Measure | Latest | Last 7 days |
|---|---|---|
| Grid carbon intensity, London (gCO2/kWh) | **{s['carbon_latest']}** ({s['carbon_index']}, {s['carbon_latest_at']}) | mean {s['carbon_7d_mean']} |
| Cleanest / dirtiest half-hour | | {s['cleanest'][0]} ({s['cleanest'][1]}) / {s['dirtiest'][0]} ({s['dirtiest'][1]}) |
| Lowest-carbon / highest-carbon hour of day (UTC, 7-day average) | | {s['cleanest_hour_utc']:02d}:00 / {s['dirtiest_hour_utc']:02d}:00 |
| Wind / gas share of generation | | {s['wind_7d']}% / {s['gas_7d']}% |
| NO2, central London (µg/m3) | {s['no2_latest']} ({s['air_latest_at']}) | mean {s['no2_7d_mean']} |
| PM2.5, central London (µg/m3) | {s['pm25_latest']} | mean {s['pm25_7d_mean']} |
| TfL lines with Good Service | {s.get('tfl_good', 'n/a')} of {s.get('tfl_lines', 'n/a')} ({s.get('tfl_latest_at', '')}) | |
| TfL disruptions at last snapshot | {issues} | |

<p align="center"><img src="docs/latest.png" width="90%"></p>
{END}"""


def update_readme(readme_text: str, section: str) -> str:
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if not pattern.search(readme_text):
        raise ValueError("README is missing the LATEST markers")
    return pattern.sub(lambda _: section, readme_text)


def badge(s: dict) -> dict:
    return {"schemaVersion": 1, "label": "London grid now",
            "message": f"{s['carbon_latest']} gCO2/kWh ({s['carbon_index']})",
            "color": BADGE_COLOURS.get(s["carbon_index"], "lightgrey")}


def build(con: sqlite3.Connection) -> dict:
    carbon, air, tfl, runs = load_frames(con)
    config.DOCS_DIR.mkdir(exist_ok=True)
    make_chart(carbon, air, config.DOCS_DIR / "latest.png")
    s = summary(carbon, air, tfl, runs)
    (config.DOCS_DIR / "badge.json").write_text(json.dumps(badge(s), indent=2) + "\n")
    if config.README.exists():
        config.README.write_text(update_readme(config.README.read_text(), render_section(s)))
    return s
