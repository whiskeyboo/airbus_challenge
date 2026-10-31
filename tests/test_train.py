import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from airbus_challenge import train

REPO = Path(__file__).resolve().parents[1]


def ts(*s):
    return pd.Series(pd.to_datetime(list(s), utc=True)).astype("datetime64[us, UTC]")


def test_scope_is_validation_and_calibration_issued_after_cutoff_never_test():
    req = pd.DataFrame(
        {
            "prediction_id": ["train", "early_val", "val", "cal", "test"],
            "target_start_utc": ts(
                "2023-06-01 12:00",
                "2024-01-01 02:00",
                "2024-03-01 12:00",
                "2024-09-01 12:00",
                "2025-03-01 12:00",
            ),
            "as_of_utc": ts(
                "2023-06-01 09:00",
                "2023-12-31 23:00",
                "2024-03-01 09:00",
                "2024-09-01 09:00",
                "2025-03-01 09:00",
            ),
        }
    )
    assert list(train.in_scope(req).prediction_id) == ["val", "cal"]
    assert train.cutoff() == pd.Timestamp("2024-01-01", tz="UTC")


def test_training_labels_read_only_requested_eligible_ids(tmp_path):
    path = tmp_path / "labels.parquet"
    base = pd.DataFrame(
        {
            "prediction_id": ["a", "b", "c", "t"],
            "target_kind": train.TARGET,
            "y_true": [10.0, 20.0, np.nan, 99.0],
            "eligible": [True, True, False, True],
        }
    )
    base.to_parquet(path)
    first = train.training_labels(path, ["a", "b", "c"])
    base.loc[3, "y_true"] = -1.0  # A test-split label changes.
    base.to_parquet(path)
    second = train.training_labels(path, ["a", "b", "c"])
    pd.testing.assert_frame_equal(first, second)
    assert list(first.prediction_id) == [
        "a",
        "b",
    ]  # Ineligible c excluded, t never read.


def test_fit_is_deterministic_with_fixed_seed():
    rng = np.random.default_rng(0)
    X = pd.DataFrame({"a": rng.normal(size=400), "b": rng.normal(size=400)})
    y = 3 * X.a + rng.normal(size=400)
    preds = [
        train.fit(X[:300], y[:300], X[300:], y[300:]).predict(X[300:]) for _ in range(2)
    ]
    np.testing.assert_array_equal(*preds)


@pytest.mark.skipif(
    not (REPO / "artifacts" / train.RUN_ID / "manifest.json").exists(),
    reason="no dev run",
)
def test_run_manifest_and_predictions_follow_the_contract():
    run = REPO / "artifacts" / train.RUN_ID
    manifest = json.loads((run / "manifest.json").read_text())
    assert pd.Timestamp(manifest["fit_cutoff_utc"]).tzinfo is not None
    assert manifest["fit_split"] == "train" and manifest["train_airports"] == [
        "KATL",
        "KDFW",
    ]
    preds = pd.read_parquet(run / "predictions.parquet")
    assert preds.target_start_utc.min() >= pd.Timestamp("2024-01-01", tz="UTC")
    assert preds.target_start_utc.max() < pd.Timestamp("2025-01-01", tz="UTC")
    assert (preds.as_of_utc >= train.cutoff()).all()
    assert (preds.p10 <= preds.p90).all()
    assert preds.prediction_id.is_unique


def test_delay_scope_excludes_test_and_fit_reads_only_requested_train_labels(tmp_path):
    req = pd.DataFrame(
        {
            "prediction_id": ["val", "test"],
            "target_start_utc": ts("2024-03-01 12:47", "2025-03-01 12:47"),
            "as_of_utc": ts("2024-03-01 09:47", "2025-03-01 09:47"),
        }
    )
    assert list(train.in_scope(req).prediction_id) == ["val"]
    path = tmp_path / "labels.parquet"
    labels = pd.DataFrame(
        {
            "prediction_id": ["tr1", "tr2", "cancelled", "test1"],
            "target_kind": train.DELAY["target"],
            "y_true": [1.0, 0.0, np.nan, 1.0],
            "eligible": [True, True, False, True],
        }
    )
    labels.to_parquet(path)
    got = train.training_labels(
        path, ["tr1", "tr2", "cancelled"], train.DELAY["target"]
    )
    assert list(got.prediction_id) == [
        "tr1",
        "tr2",
    ]  # Cancelled excluded; test never read.
