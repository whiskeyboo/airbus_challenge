from pathlib import Path

import yaml


def test_airport_headings():
    config = yaml.safe_load(Path("configs/airports.yaml").read_text())
    headings = {icao: a["runway_heading_deg"] for icao, a in config["airports"].items()}
    assert headings == {"KATL": 80, "KDFW": 180}
