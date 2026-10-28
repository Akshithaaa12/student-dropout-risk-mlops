"""
run_pipeline.py -- End-to-end pipeline orchestrator.

Runs, in order: generate_synthetic_sources (optional, once) -> ingest ->
validate_clean -> transform_load, exactly mirroring the task graph
defined in dags/student_pipeline_dag.py (see that file for how the same
three stages would be scheduled inside a real Apache Airflow DAG).

This script is what you run for the live Part 1 demo ("demonstrate one
successful end-to-end pipeline execution"): a single command takes the
raw source files all the way to the populated SQLite database, with a
timestamped run log written to logs/pipeline_run_log.txt.
"""

import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ingest
import validate_clean
import transform_load

BASE_DIR = Path(__file__).resolve().parents[1]
RUN_LOG = BASE_DIR / "logs" / "pipeline_run_log.txt"


def _log(msg: str):
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line)
    with open(RUN_LOG, "a") as f:
        f.write(line + "\n")


def run_stage(name, fn):
    _log(f"STAGE START: {name}")
    t0 = time.time()
    try:
        result = fn()
        elapsed = time.time() - t0
        _log(f"STAGE OK:    {name} ({elapsed:.2f}s)")
        return result
    except Exception:
        elapsed = time.time() - t0
        _log(f"STAGE FAILED:{name} ({elapsed:.2f}s)")
        _log(traceback.format_exc())
        raise


def main():
    _log("=" * 60)
    _log("PIPELINE RUN START")
    run_stage("ingest (source -> raw)", ingest.run)
    run_stage("validate_clean (raw -> cleaned)", validate_clean.run)
    run_stage("transform_load (cleaned -> analytical + SQLite)", transform_load.run)
    _log("PIPELINE RUN COMPLETE")
    _log("=" * 60)


if __name__ == "__main__":
    main()
