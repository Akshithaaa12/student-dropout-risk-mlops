# Student Performance & Dropout-Risk Prediction System -- Part 1 + Part 2

**Course:** Data Engineering and MLOps &nbsp;|&nbsp; **Mode:** Individual project
**Part 1:** data pipeline (ingestion -> validation/cleaning -> transformation &
storage -> analytics dashboard). **Part 2:** the MLOps layer on top of it
(ML dataset -> training with MLflow tracking + model registry -> FastAPI serving
-> Docker -> drift monitoring and retraining criteria). Jump to "Part 2 (MLOps)".

## What this is
A unified data pipeline that pulls together a real academic-performance
dataset (UCI Student Performance) with simulated attendance, LMS
activity and assignment-submission exports, cleans and validates it,
loads it into a SQLite analytical warehouse, and surfaces it through a
5-view Streamlit dashboard -- including a transparent, rule-based
high-risk student list. Part 2 adds a trained classifier on top of the same data.

## Project layout
```
data/source_files/   raw external sources (never modified by the pipeline)
data/raw/            Raw layer      (ingest.py output)
data/staging/        (reserved for Part 2 feature-engineering staging)
data/cleaned/        Cleaned layer  (validate_clean.py output)
data/analytical/     Analytical layer / data mart (transform_load.py output)
db/                  SQLite warehouse (student_performance.db)
scripts/             ETL scripts + orchestrator
dags/                Airflow DAG definition (documentation / optional)
dashboard/           Streamlit dashboard (app.py)
docs/                Architecture diagram, data dictionary, validation
                     rules, data sources, schema, project report
logs/                Extraction log, rejected-records log, pipeline run log
screenshots/         Execution-evidence screenshots for submission
```

## Setup
Requires Python 3.10+.

```bash
cd student-performance-pipeline
python3 -m venv .venv && source .venv/bin/activate   # optional but recommended
pip install -r requirements.txt
```

No database server, API keys or credentials are required for Part 1
(SQLite is a single file). See `.env.example` for the environment
variables the pipeline reads (`DB_PATH`) and the placeholders it would
need if you later point it at a real ERP/LMS or PostgreSQL (Part 2).

## Run the full pipeline (the "one successful end-to-end execution" demo)
```bash
# (Re)generate the simulated attendance/LMS/assignment sources.
# Safe to skip if data/source_files/{attendance,lms,assignments}/*.csv
# already exist -- only needed once, or if you want a different seed.
python scripts/generate_synthetic_sources.py

# Run ingestion -> validation/cleaning -> transform & load, in one command
python scripts/run_pipeline.py
```
Expected output: per-stage `STAGE OK` lines with timings, ending in
`PIPELINE RUN COMPLETE`, plus:
- `logs/extraction_log.csv` -- what was ingested, when, row counts, status
- `logs/rejected_records.csv` -- every row dropped/corrected during cleaning, with a reason
- `logs/attendance_completeness_gaps.csv` -- students missing attendance months
- `logs/pipeline_run_log.txt` -- timestamped run log
- `db/student_performance.db` -- populated SQLite warehouse (10 tables)

Re-running is safe: every stage is idempotent (raw/cleaned/analytical
outputs and the SQLite tables are fully rewritten each run).

## Launch the dashboard
```bash
streamlit run dashboard/app.py
```
Opens at `http://localhost:8501`. Five views (sidebar radio): attendance
vs marks, subject-wise pass/fail, department & semester performance,
high-risk student list, and a per-student profile with a simple
rule-based intervention suggestion.

## Airflow (Docker)
`dags/student_pipeline_dag.py` is the 6-task DAG (`ingest -> validate_clean ->
transform_load -> build_ml_dataset -> train_and_register_model -> monitor_drift`).
It runs in its own container (Airflow 2.10 + the ML libraries):
```bash
docker compose --profile airflow up --build airflow
```
Open `http://localhost:8080` (user `admin`, password `admin`), open
`student_performance_pipeline` and press Trigger. Airflow logs to its own
MLflow DB (`mlstore/airflow_mlflow.db`). Without Docker,
`python scripts/run_pipeline.py` / `scripts/run_mlops.py` run the same stages directly.

## Documentation index
- `docs/architecture_diagram.png` -- pipeline flow diagram (regenerate with `docs/generate_architecture_diagram.py`, requires system Graphviz)
- `docs/data_dictionary.md` -- every table/column, with real vs. synthetic vs. derived provenance
- `docs/validation_rules.md` -- every cleaning/validation rule and its rejection-log reason code
- `docs/data_sources.md` -- dataset origin and access instructions
- `docs/schema.sql` -- full database DDL (logical star schema)
- `docs/report.docx` -- the ~8-10 page Part 1 project report
- `docs/ml_design.md`, `docs/monitoring_policy.md`, `docs/api_reference.md` -- Part 2 design, drift/retraining policy, API contract

## Part 2 (MLOps)

**Problem:** predict at mid-semester which students are on course to fail
(`G3 < 10`, used as a proxy for dropout risk since the data has no literal dropout
column), early enough for a mentor to intervene. Details and caveats: `docs/ml_design.md`.

```
Part 1 mart + cleaned records
        |  mlops/dataset.py      leak-free ML dataset (data/ml/, table ml_training_dataset)
        v
 mlops/train.py ---> MLflow (tracking + registry, alias "champion") ---> models/champion.joblib
        |                                                                     |
        |                                                                     v
 mlops/monitoring.py <--- logs/prediction_log.csv <--- api/main.py (FastAPI, Docker)
        |
        v   PSI / KS drift + retraining triggers (docs/monitoring_policy.md)
 retrain (mlops.train) -> challenger vs champion -> promote
```

### Run it (after Part 1: `python scripts/run_pipeline.py`)
```bash
pip install -r requirements.txt

python scripts/run_mlops.py            # dataset -> train + register -> drift check
#   or step by step:
python -m mlops.dataset
python -m mlops.train                  # prints the model comparison; ~35 s

mlflow ui --port 5001 --backend-store-uri sqlite:///mlstore/mlflow.db   # http://localhost:5001
uvicorn api.main:app --reload --port 8000                   # http://localhost:8000/docs
streamlit run dashboard/app.py                              # view "6. ML Model ..."

python -m mlops.monitoring --simulate-drift   # DEMO: fabricated shifted batch, clearly labelled
python -m mlops.monitoring                    # real check on logs/prediction_log.csv
python -m pytest tests -q                     # 15 tests (API, dataset/leakage, model, monitoring)
```

Try a prediction:
```bash
curl -X POST localhost:8000/predict -H 'content-type: application/json' \
  -d '{"student_id":"DEMO1","previous_semester_score":8,"avg_internal_marks":8.5,"attendance_pct":62,"failures":1}'
```

### Docker
```bash
docker compose --profile train run --rm trainer   # builds the image, builds dataset, trains, registers
docker compose up --build api                     # serve on :8000
docker compose up mlflow                          # MLflow UI on :5001
docker compose --profile monitor run --rm monitor
```
Train either locally or in Docker, not both against the same `mlstore/` (MLflow stores absolute artifact paths).
Retrain on your own machine after cloning: model files are not committed because pickles
depend on the exact scikit-learn version.

### Tracking on DagsHub (optional)
Set `MLFLOW_TRACKING_URI`, `MLFLOW_TRACKING_USERNAME`, `MLFLOW_TRACKING_PASSWORD` (see `.env.example`)
and re-run `python -m mlops.train`; runs and the registered model appear in the DagsHub repo.

### Part 2 layout
```
mlops/        config (feature contract), dataset, modeling, train, tracking, monitoring
api/          FastAPI app + Pydantic schemas
scripts/run_mlops.py   end-to-end Part 2 runner (same steps as the Airflow tasks)
tests/        pytest suite
Dockerfile, docker-compose.yml, requirements-docker.txt
docs/ml_design.md  docs/monitoring_policy.md  docs/api_reference.md
reports/      model_comparison.csv, ROC/PR/SHAP/confusion plots, drift reports
```
