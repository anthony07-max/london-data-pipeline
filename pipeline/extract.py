"""Extract: call the public APIs with timeouts and retries. Returns raw JSON."""
from datetime import datetime, timedelta, timezone

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import config


def _session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=4, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["GET"])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers["User-Agent"] = config.USER_AGENT
    return s


def fetch_carbon(days: int = 2, now: datetime | None = None) -> dict:
    """Half-hourly carbon intensity and generation mix for London for the last `days` days.
    The API allows at most 14 days per request."""
    now = now or datetime.now(timezone.utc)
    end = now.replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=min(days, 14))
    url = config.CARBON_URL.format(start=start.strftime("%Y-%m-%dT%H:%MZ"), end=end.strftime("%Y-%m-%dT%H:%MZ"))
    r = _session().get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_air_quality(days: int = 2) -> dict:
    """Hourly modelled air quality for central London for the last `days` days (up to the current hour)."""
    params = {"latitude": config.LONDON_LAT, "longitude": config.LONDON_LON, "hourly": ",".join(config.AIR_VARS),
              "past_days": min(days, 92), "forecast_days": 1, "timezone": "UTC"}
    r = _session().get(config.AIR_URL, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_tfl_status() -> list:
    """Current status of every Tube, Elizabeth line, Overground and DLR line."""
    r = _session().get(config.TFL_URL.format(modes=",".join(config.TFL_MODES)), timeout=30)
    r.raise_for_status()
    return r.json()
