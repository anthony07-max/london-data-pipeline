"""Central configuration: endpoints, locations and paths."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "london.db"
EXPORT_DIR = ROOT / "data" / "exports"
DOCS_DIR = ROOT / "docs"
README = ROOT / "README.md"

# National Energy System Operator (NESO) Carbon Intensity API, region 13 = London (UKPN London)
CARBON_URL = "https://api.carbonintensity.org.uk/regional/intensity/{start}/{end}/regionid/13"
# Open-Meteo air quality API (CAMS European model), central London
AIR_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
LONDON_LAT, LONDON_LON = 51.5072, -0.1276
AIR_VARS = ["pm10", "pm2_5", "nitrogen_dioxide", "ozone", "european_aqi"]
# Transport for London unified API (no key needed at this volume)
TFL_URL = "https://api.tfl.gov.uk/Line/Mode/{modes}/Status"
TFL_MODES = ["tube", "elizabeth-line", "overground", "dlr"]

USER_AGENT = "london-data-pipeline (github.com/anthony07-max/london-data-pipeline)"
