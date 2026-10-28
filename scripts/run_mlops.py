"""
Run the whole Part 2 flow end to end (after Part 1 has produced the mart):

    python scripts/run_mlops.py            # dataset -> train/register -> drift check
    python scripts/run_mlops.py --skip-monitor

Mirrors the Airflow tasks in dags/student_pipeline_dag.py:
    build_ml_dataset >> train_and_register_model >> monitor_drift
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mlops import config as C  # noqa: E402


def log(msg: str) -> None:
    C.LOG_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {msg}"
    print(line)
    with open(C.LOG_DIR / "mlops_run_log.txt", "a") as fh:
        fh.write(line + "\n")


def build_ml_dataset():
    from mlops import dataset
    dataset.main()


def _run_module(module: str, *args: str) -> None:
    """Run `python -m <module>` in a child process and echo its output.

    Inside an Airflow task, stderr is replaced by Airflow's log writer and MLflow's
    logging then recurses into Airflow's secret masker (RecursionError). Patching the
    streams in-process avoids the crash but leaves Airflow's `dill` hooks active, so the
    exported champion.joblib needs `dill` to load. A child process has plain stdio and
    writes a clean pickle; its output still appears in the task log.
    """
    proc = subprocess.run(
        [sys.executable, "-m", module, *args],
        cwd=str(C.BASE_DIR), env={**os.environ, "PYTHONPATH": str(C.BASE_DIR)},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    print(proc.stdout)
    if proc.returncode != 0:
        raise RuntimeError(f"{module} exited with code {proc.returncode}")


def _under_airflow() -> bool:
    return "AIRFLOW_CTX_DAG_ID" in os.environ


def train_and_register_model():
    if _under_airflow():
        _run_module("mlops.train")
        meta = json.loads((C.MODEL_DIR / "champion_meta.json").read_text())
        return {"winner": meta.get("algorithm"), "threshold": meta.get("threshold"),
                "test": meta.get("metrics_test_operating_threshold")}
    from mlops import train
    return train.main(register=True)


def monitor_drift():
    """Skips quietly when no real traffic has been logged yet (nothing to compare)."""
    if not C.PREDICTION_LOG.exists():
        log("monitor_drift: no prediction log yet, nothing to compare (send requests to the API first)")
        return None
    if _under_airflow():
        _run_module("mlops.monitoring")
        return None
    from mlops import monitoring
    rep = monitoring.run(simulated=False)
    monitoring.print_report(rep)
    return rep


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-monitor", action="store_true")
    a = ap.parse_args()
    for name, fn in [("build_ml_dataset", build_ml_dataset), ("train_and_register_model", train_and_register_model)] + \
                    ([] if a.skip_monitor else [("monitor_drift", monitor_drift)]):
        t = time.time()
        log(f"START {name}")
        fn()
        log(f"DONE  {name} ({time.time() - t:.1f}s)")


if __name__ == "__main__":
    main()
