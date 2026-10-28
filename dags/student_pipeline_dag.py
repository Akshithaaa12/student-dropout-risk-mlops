"""
student_pipeline_dag.py -- Apache Airflow DAG definition for the
Student Performance & Dropout-Risk data pipeline.

This DAG wraps the exact same stage functions used by
scripts/run_pipeline.py (ingest.run -> validate_clean.run ->
transform_load.run), so the orchestration logic is defined once and
shared between "run it directly for a demo" and "schedule it in
Airflow" execution paths.

HOW TO ACTUALLY RUN THIS IN AIRFLOW (not required for the Part 1 demo,
documented here for completeness / the report):
    1. pip install apache-airflow
    2. export AIRFLOW_HOME=~/airflow
    3. airflow db migrate
    4. Copy/symlink this file into $AIRFLOW_HOME/dags/, and make sure
       the `scripts/` folder (ingest.py, validate_clean.py,
       transform_load.py) is importable, e.g. by adding the project
       root to PYTHONPATH or installing it as a local package.
    5. airflow standalone
       -> open the Airflow UI, unpause "student_performance_pipeline",
          trigger a run.

For tonight's live demo, scripts/run_pipeline.py runs the identical
three stages directly with no Airflow install required -- that is the
"approved equivalent ETL workflow" the assignment brief allows as an
alternative to a running Airflow instance.
"""

from datetime import datetime, timedelta
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT))  # so `import mlops` works for the Part 2 tasks

from airflow import DAG
from airflow.operators.python import PythonOperator

import ingest
import validate_clean
import transform_load
import run_mlops  # Part 2: dataset -> train/register -> drift monitoring

default_args = {
    "owner": "akshitha",
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="student_performance_pipeline",
    description="Ingest -> validate/clean -> transform & load -> ML dataset -> train/register -> drift check",
    default_args=default_args,
    schedule="@daily",
    start_date=datetime(2026, 9, 1),
    catchup=False,
    tags=["mlops-assignment", "part1", "part2", "etl", "ml"],
) as dag:

    ingest_task = PythonOperator(
        task_id="ingest_source_to_raw",
        python_callable=ingest.run,
    )

    validate_task = PythonOperator(
        task_id="validate_and_clean_raw_to_cleaned",
        python_callable=validate_clean.run,
    )

    transform_load_task = PythonOperator(
        task_id="transform_and_load_to_analytical_db",
        python_callable=transform_load.run,
    )

    # ---- Part 2 (MLOps) tasks ------------------------------------------------
    ml_dataset_task = PythonOperator(
        task_id="build_ml_dataset",
        python_callable=run_mlops.build_ml_dataset,
    )

    train_task = PythonOperator(
        task_id="train_and_register_model",
        python_callable=run_mlops.train_and_register_model,
    )

    monitor_task = PythonOperator(
        task_id="monitor_drift",
        python_callable=run_mlops.monitor_drift,
    )

    (ingest_task >> validate_task >> transform_load_task
     >> ml_dataset_task >> train_task >> monitor_task)
