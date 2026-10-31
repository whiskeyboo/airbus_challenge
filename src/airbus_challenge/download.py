import hashlib
import os
from pathlib import Path

import gdown
from dotenv import load_dotenv

RAW = Path("data/raw")
CSV_NAME = "Flight_Data_With_Weather_Final.csv"


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
        gdown.download_folder(id=os.environ["DATA_GDRIVE_FOLDER_ID"], output=str(RAW), quiet=False)
    return path


if __name__ == "__main__":
    p = download_provided_csv()
    print(p, p.stat().st_size, "bytes, sha256", sha256(p))
