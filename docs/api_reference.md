# Prediction API (FastAPI)

Start: `uvicorn api.main:app --port 8000`. Interactive docs at `/docs`. Loads `models/champion.joblib`
(or `models:/student-dropout-risk@champion` from MLflow when `USE_MLFLOW_REGISTRY=1`).

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness, `model_loaded`, model source |
| GET | `/model-info` | algorithm, registry version, threshold, test metrics, feature list |
| POST | `/predict` | one student |
| POST | `/predict/batch` | `{"students": [...]}`, 1 to 500 |
| GET | `/stats` | in-memory request count, share flagged, average latency |

## Request
Only `previous_semester_score` (0 to 20) is required. Every other feature is optional; a missing one is imputed with
the training median and its availability flag set to 0. Unknown fields and out-of-range values return HTTP 422.
Feature names and ranges are in `api/schemas.py` and `docs/data_dictionary.md`.

## Response
```json
{"student_id": "DEMO1", "at_risk_probability": 0.8693, "at_risk": true, "risk_band": "High",
 "threshold": 0.64,
 "top_factors": [{"feature": "avg_internal_marks", "label": "Average internal marks", "impact": 0.4251}, ...],
 "model_version": "2"}
```
`risk_band`: High if probability >= threshold, Medium if >= 0.30, else Low. `top_factors` come from occlusion (each
feature swapped for the training average, change in probability), so no SHAP is needed at serving time.

## Side effect
Each prediction is appended to `logs/prediction_log.csv` (timestamp, id, features, probability, flag) for drift
monitoring. The file holds student identifiers, so keep `logs/` out of git (already in `.gitignore`).
