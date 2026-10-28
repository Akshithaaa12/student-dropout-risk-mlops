"""
FastAPI model-serving service for the dropout-risk model (Part 2).

Run locally:   uvicorn api.main:app --reload --port 8000
Docs (Swagger): http://localhost:8000/docs

Endpoints
  GET  /health         liveness + whether a model is loaded
  GET  /model-info     algorithm, version, threshold, test metrics, features
  POST /predict        one student -> probability, band, top factors
  POST /predict/batch  up to 500 students
  GET  /stats          in-memory request counters (latency, share flagged)

Every prediction is appended to logs/prediction_log.csv; mlops/monitoring.py
reads that file to detect data drift and prediction drift.
"""

import csv
import json
import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException

from api.schemas import BatchRequest, BatchResponse, Factor, Prediction, StudentFeatures
from mlops import config as C

LOG_LOCK = threading.Lock()
STATE = {"model": None, "meta": None, "ref": None, "source": None,
         "n_requests": 0, "n_predictions": 0, "n_flagged": 0, "latency_ms_sum": 0.0}

BAND_LOW_CUTOFF = 0.30


def prediction_log_path() -> Path:
    return Path(os.environ.get("PREDICTION_LOG", C.PREDICTION_LOG))


def load_model() -> None:
    """Load the exported champion bundle. Optionally pull from the MLflow registry
    instead (USE_MLFLOW_REGISTRY=1) so a promotion in the registry is picked up
    on the next restart without rebuilding the image."""
    meta_path, model_path = Path(os.environ.get("CHAMPION_META", C.CHAMPION_META)), Path(os.environ.get("CHAMPION_PATH", C.CHAMPION_PATH))
    if os.environ.get("USE_MLFLOW_REGISTRY") == "1":
        import mlflow
        mlflow.set_tracking_uri(C.MLFLOW_TRACKING_URI)
        STATE["model"] = mlflow.sklearn.load_model(f"models:/{C.REGISTERED_MODEL_NAME}@{C.CHAMPION_ALIAS}")
        STATE["source"] = f"mlflow registry models:/{C.REGISTERED_MODEL_NAME}@{C.CHAMPION_ALIAS}"
    elif model_path.exists():
        STATE["model"] = joblib.load(model_path)
        STATE["source"] = f"bundle {model_path.name}"
    else:
        return
    STATE["meta"] = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    ref_path = Path(os.environ.get("REFERENCE_STATS", C.REFERENCE_STATS))
    STATE["ref"] = json.loads(ref_path.read_text()) if ref_path.exists() else None


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_model()
    yield


app = FastAPI(title="Student Dropout-Risk API", version="1.0.0",
              description="Serves the champion model from the MLflow registry bundle. "
                          "Predictions support early-warning conversations; they are not decisions.",
              lifespan=lifespan)


# ---------------------------------------------------------------- helpers ----
def _require_model():
    if STATE["model"] is None:
        raise HTTPException(503, "No model loaded. Run `python -m mlops.train` first.")


def _to_frame(students) -> pd.DataFrame:
    rows = []
    for s in students:
        d = s.model_dump()
        d.pop("student_id", None)
        d["attendance_data_available"] = int(d["attendance_pct"] is not None)
        d["lms_data_available"] = int(d["lms_engagement_score"] is not None)
        d["assignment_data_available"] = int(d["assignment_completion_rate"] is not None)
        rows.append(d)
    df = pd.DataFrame(rows).reindex(columns=C.FEATURES)
    return df.astype(float)  # None -> NaN; imputer inside the pipeline handles it


def _band(p: float, thr: float) -> str:
    return "High" if p >= thr else ("Medium" if p >= BAND_LOW_CUTOFF else "Low")


def _typical_row() -> pd.Series:
    ref = (STATE["ref"] or {}).get("features", {})
    return pd.Series({f: ref.get(f, {}).get("mean", 0.0) for f in C.FEATURES})


def _top_factors(X: pd.DataFrame, base: np.ndarray, k=3):
    """Occlusion explanation: swap one feature at a time for the training average and
    see how far the risk drops. Works for any model, no SHAP needed at serving time."""
    typical = _typical_row()
    out = []
    for i in range(len(X)):
        variants = pd.concat([X.iloc[[i]]] * len(C.FEATURES), ignore_index=True)
        for j, f in enumerate(C.FEATURES):
            variants.loc[j, f] = typical[f]
        p_alt = STATE["model"].predict_proba(variants)[:, 1]
        impact = base[i] - p_alt
        order = np.argsort(-np.abs(impact))[:k]
        out.append([Factor(feature=C.FEATURES[j], label=C.FEATURE_LABELS[C.FEATURES[j]],
                           impact=round(float(impact[j]), 4)) for j in order if abs(impact[j]) > 1e-4])
    return out


def _log_predictions(students, X, proba, flagged):
    path = prediction_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with LOG_LOCK:
        new = not path.exists()
        with open(path, "a", newline="") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(["timestamp", "student_id", *C.FEATURES, "probability", "at_risk"])
            ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
            for s, (_, row), p, f in zip(students, X.iterrows(), proba, flagged):
                w.writerow([ts, s.student_id or "", *[("" if pd.isna(v) else v) for v in row.tolist()],
                            round(float(p), 5), int(f)])


def _predict(students):
    _require_model()
    t0 = time.perf_counter()
    X = _to_frame(students)
    proba = STATE["model"].predict_proba(X)[:, 1]
    thr = float(STATE["meta"].get("threshold", 0.5))
    flagged = proba >= thr
    factors = _top_factors(X, proba)
    version = STATE["meta"].get("registry_version")
    preds = [Prediction(student_id=s.student_id, at_risk_probability=round(float(p), 4),
                        at_risk=bool(f), risk_band=_band(p, thr), threshold=thr,
                        top_factors=fx, model_version=str(version) if version is not None else None)
             for s, p, f, fx in zip(students, proba, flagged, factors)]
    _log_predictions(students, X, proba, flagged)
    STATE["n_requests"] += 1
    STATE["n_predictions"] += len(preds)
    STATE["n_flagged"] += int(flagged.sum())
    STATE["latency_ms_sum"] += (time.perf_counter() - t0) * 1000
    return preds


# -------------------------------------------------------------- endpoints ----
@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": STATE["model"] is not None, "source": STATE["source"]}


@app.get("/model-info")
def model_info():
    _require_model()
    m = STATE["meta"]
    return {k: m.get(k) for k in ("model_name", "algorithm", "registry_version", "alias", "trained_at",
                                  "threshold", "target_definition", "features",
                                  "metrics_test_operating_threshold", "cv")}


@app.post("/predict", response_model=Prediction)
def predict(student: StudentFeatures):
    return _predict([student])[0]


@app.post("/predict/batch", response_model=BatchResponse)
def predict_batch(req: BatchRequest):
    preds = _predict(req.students)
    return BatchResponse(count=len(preds), predictions=preds)


@app.get("/stats")
def stats():
    n = max(STATE["n_requests"], 1)
    return {"requests": STATE["n_requests"], "predictions": STATE["n_predictions"],
            "flagged_share": round(STATE["n_flagged"] / max(STATE["n_predictions"], 1), 4),
            "avg_latency_ms": round(STATE["latency_ms_sum"] / n, 2)}
