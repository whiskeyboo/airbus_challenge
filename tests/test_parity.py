"""Offline/served parity (TEMPORAL_RULES §7 test 10): the stored feature row for pinned real
requests equals a fresh recomputation through features.request_snapshots at that exact as_of."""

from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds
import pytest

from airbus_challenge import features

REPO = Path(__file__).resolve().parents[1]
PROCESSED = REPO / "data/processed"
PINNED = {
    "cab921e6a2cd0702afe2d4e9270f7a4496f4e3a0737271d479acad694c9ab82f": "KDFW throughput, on the hour, 2024-05-27 18Z h6",
    "0a3aed8fc4da1659511ab1e49ae684a6a5aa2791eab18fbd6fb14652c9932d8a": "KDFW flight, off the hour (17:58Z)",
    "012848bffb134423c67035db83f280a45fa3e30ec1a41e41a8509dce0bfa8729": "metar_stale (+ metar_cor_skipped)",
    "009adf19389a44051d6cc28e040193c481195dd74214776a092868dede684550": "metar_cor_skipped",
    "01965a8ca884568c31ccb089e402d461d52783e18f0f2641ef5075efbe91ac14": "taf_conflict_fallback",
    "f392e1c574ebfc1dd40dcbace9385e621568e4e9c59118f9aa14611b6c9f2d2d": "KATL 2023-08-11 thunderstorm, h12",
}  # fmt: skip
NEEDED = ["feature_snapshots.parquet", "feature_lineage.parquet",
          "weather_observations.parquet", "weather_forecasts.parquet"]  # fmt: skip


@pytest.mark.skipif(
    not all((PROCESSED / n).exists() for n in NEEDED), reason="needs data/"
)
def test_stored_snapshots_equal_fresh_recomputation_for_pinned_requests():
    stored = (
        ds.dataset(PROCESSED / "feature_snapshots.parquet")
        .to_table(filter=ds.field("prediction_id").isin(list(PINNED)))
        .to_pandas()
        .set_index("prediction_id")
    )
    assert set(stored.index) == set(PINNED)
    expected_codes = {"metar_stale", "metar_cor_skipped", "taf_conflict_fallback"}
    assert expected_codes <= {c for r in stored.reason_codes for c in r}
    obs = pd.read_parquet(PROCESSED / "weather_observations.parquet")
    fc = pd.read_parquet(PROCESSED / "weather_forecasts.parquet")
    req = stored.reset_index()[features.REQUEST_COLUMNS]
    fresh, lineage = features.request_snapshots(obs, fc, req)
    fresh = fresh.set_index("prediction_id").loc[stored.index]

    for col in ["snapshot_key", "window_end_utc", "feature_version", "status"]:
        assert (fresh[col] == stored[col]).all(), col
    assert (
        fresh.reason_codes.map(list).tolist() == stored.reason_codes.map(list).tolist()
    )
    for col in features.FEATURES:
        a, b = stored[col], fresh[col]
        if a.dtype.kind == "f":
            np.testing.assert_allclose(
                a.astype("float64"),
                b.astype("float64"),
                rtol=1e-6,
                atol=1e-5,
                err_msg=col,
            )
        else:
            assert (
                a.astype(object).where(a.notna(), None).tolist()
                == b.astype(object).where(b.notna(), None).tolist()
            ), col

    stored_lineage = (
        ds.dataset(PROCESSED / "feature_lineage.parquet")
        .to_table(filter=ds.field("snapshot_key").isin(list(stored.snapshot_key)))
        .to_pandas()
    )
    key = ["snapshot_key", "feature_group", "source_record_id", "transform_version"]
    as_set = lambda df: set(map(tuple, df[key].astype(str).to_numpy()))
    assert as_set(lineage) == as_set(stored_lineage)
