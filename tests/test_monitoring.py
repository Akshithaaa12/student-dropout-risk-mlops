import numpy as np
import pandas as pd

from mlops import config as C
from mlops import monitoring


def test_psi_zero_for_identical_and_large_for_shift():
    a = [0.25, 0.25, 0.25, 0.25]
    assert monitoring.psi(a, a) == 0
    assert monitoring.psi(a, [0.7, 0.1, 0.1, 0.1]) > monitoring.PSI_SEVERE


def test_simulated_drift_triggers_retrain(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "REPORT_DIR", tmp_path)
    rep = monitoring.run(simulated=True, log_to_mlflow=False)
    assert rep["simulated"] is True
    assert rep["status"] == "RETRAIN_RECOMMENDED"
    assert any(t.startswith("T1") for t in rep["triggers"])
    assert rep["feature_drift"][0]["psi"] > monitoring.PSI_SEVERE


def test_unshifted_batch_is_healthy(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "REPORT_DIR", tmp_path)
    df = monitoring.score_frame(pd.read_csv(C.ML_DATASET_CSV).sample(300, random_state=3))
    log = tmp_path / "log.csv"
    df.to_csv(log, index=False)
    monkeypatch.setattr(C, "PREDICTION_LOG", log)
    rep = monitoring.run(simulated=False, log_to_mlflow=False)
    assert rep["status"] == "healthy", rep["triggers"]


def test_too_few_rows_is_not_judged(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "REPORT_DIR", tmp_path)
    log = tmp_path / "log.csv"
    monitoring.score_frame(pd.read_csv(C.ML_DATASET_CSV).head(5)).to_csv(log, index=False)
    monkeypatch.setattr(C, "PREDICTION_LOG", log)
    assert monitoring.run(log_to_mlflow=False)["status"] == "insufficient_data"
