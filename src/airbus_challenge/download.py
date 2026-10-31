import hashlib
import http.client
import json
import os
import shutil
import threading
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

import gdown
import yaml
from dotenv import load_dotenv

RAW = Path("data/raw")
CSV_NAME = "Flight_Data_With_Weather_Final.csv"
MANIFEST = RAW / "manifest.json"
AIRPORTS = Path("configs/airports.yaml")
EXPERIMENT = Path("configs/experiment.yaml")

BTS_URL = (
    "https://transtats.bts.gov/PREZIP/"
    "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}.zip"
)
IEM_URL = "https://mesonet.agron.iastate.edu/cgi-bin/request"
IEM_THROTTLE_S = 1.1  # IEM throttles each IP to one request per second.
BTS_WORKERS = 3
RETRY_ATTEMPTS = 6
RETRY_CODES = {429, 500, 502, 503, 504}
# The first UTC hours and trailing weather features need records from before train start.
LOOKBACK = timedelta(days=2)

_manifest_lock = threading.Lock()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download_provided_csv() -> Path:
    load_dotenv()
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / CSV_NAME
    if not path.exists():
        gdown.download_folder(
            id=os.environ["DATA_GDRIVE_FOLDER_ID"], output=str(RAW), quiet=False
        )
    return path


def study_window() -> tuple[datetime, datetime]:
    splits = yaml.safe_load(EXPERIMENT.read_text())["splits"]
    start = datetime.fromisoformat(splits["train"]["start"]).replace(tzinfo=UTC)
    end = datetime.fromisoformat(splits["test"]["end"]).replace(tzinfo=UTC)
    return start - LOOKBACK, end


def months(start: datetime, end: datetime) -> list[tuple[int, int]]:
    last = end - timedelta(microseconds=1)
    span = range(start.year * 12 + start.month - 1, last.year * 12 + last.month)
    return [(m // 12, m % 12 + 1) for m in span]


def airport(icao: str) -> dict:
    return yaml.safe_load(AIRPORTS.read_text())["airports"][icao]


def _iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _stamp(start: datetime, end: datetime) -> str:
    return f"{start:%Y%m%d}_{end:%Y%m%d}"


def metar_job(icao: str, start: datetime, end: datetime) -> tuple[str, Path]:
    query = urlencode(
        {
            "station": airport(icao)["iem_station"],
            "data": "all",
            "sts": _iso(start),
            "ets": _iso(end),
            "tz": "Etc/UTC",
            "format": "onlycomma",
            "latlon": "no",
            "elev": "no",
            "missing": "null",
            "report_type": [3, 4],  # Routine and special reports.
            "direct": "no",
        },
        doseq=True,
    )
    return (
        f"{IEM_URL}/asos.py?{query}",
        RAW / "metar" / f"metar_{icao}_{_stamp(start, end)}.csv",
    )


def taf_job(icao: str, start: datetime, end: datetime) -> tuple[str, Path]:
    # IEM filters this range on issuance time, not forecast validity.
    query = urlencode(
        {
            "station": icao,
            "sts": _iso(start),
            "ets": _iso(end),
            "tz": "Etc/UTC",
            "fmt": "csv",
        }
    )
    return (
        f"{IEM_URL}/taf.py?{query}",
        RAW / "taf" / f"taf_{icao}_{_stamp(start, end)}.csv",
    )


def bts_job(year: int, month: int) -> tuple[str, Path]:
    return BTS_URL.format(
        year=year, month=month
    ), RAW / "bts" / f"bts_{year}_{month:02d}.zip"


def _is_complete(path: Path) -> bool:
    if path.name.endswith(".zip.part"):
        return zipfile.is_zipfile(path)
    with path.open(encoding="utf8", errors="replace") as f:
        return f.readline().startswith("station,") and bool(f.readline())


def record(path: Path, url: str, retrieved_at: str | None) -> None:
    entry = {
        "url": url,
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "retrieved_at_utc": retrieved_at,
    }
    with _manifest_lock:
        manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
        manifest[path.relative_to(RAW).as_posix()] = entry
        MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True))


def fetch(job: tuple[str, Path]) -> Path:
    url, path = job
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(f"{path.name}.part")
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            with (
                urllib.request.urlopen(request, timeout=600) as response,
                part.open("wb") as f,
            ):
                shutil.copyfileobj(response, f, 1 << 20)
            if not _is_complete(part):
                raise ValueError(f"incomplete or invalid response for {path.name}")
            break
        except urllib.error.HTTPError as e:
            if e.code not in RETRY_CODES or attempt == RETRY_ATTEMPTS:
                raise
        except (OSError, ValueError, http.client.HTTPException):
            if attempt == RETRY_ATTEMPTS:
                raise
        print(f"retry {attempt}/{RETRY_ATTEMPTS - 1} for {path.name}", flush=True)
        time.sleep(5 * 2**attempt)
    part.replace(path)
    record(path, url, datetime.now(UTC).isoformat(timespec="seconds"))
    print(path, path.stat().st_size, "bytes", flush=True)
    return path


def download_weather(icao: str, start: datetime, end: datetime) -> list[Path]:
    paths = []
    for job in (metar_job(icao, start, end), taf_job(icao, start, end)):
        paths.append(fetch(job))
        time.sleep(IEM_THROTTLE_S)
    return paths


def download_bts(start: datetime, end: datetime) -> list[Path]:
    with ThreadPoolExecutor(BTS_WORKERS) as pool:
        return list(pool.map(fetch, [bts_job(y, m) for y, m in months(start, end)]))


def download_all() -> None:
    csv = download_provided_csv()
    print(csv, csv.stat().st_size, "bytes, sha256", sha256(csv), flush=True)
    record(csv, "google-drive-folder", None)
    start, end = study_window()
    icaos = yaml.safe_load(AIRPORTS.read_text())["airports"]
    for icao in icaos:
        download_weather(icao, start, end)
    download_bts(start, end)


if __name__ == "__main__":
    download_all()
