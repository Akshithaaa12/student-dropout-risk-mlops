"""
Send demo prediction requests to a running API so logs/prediction_log.csv fills up
(the drift monitor needs at least 30 logged predictions).

    python scripts/send_demo_traffic.py                 # 100 normal students
    python scripts/send_demo_traffic.py --drifted       # 100 students from a simulated bad semester
    python scripts/send_demo_traffic.py --url http://localhost:8000 --n 60

This is DEMO traffic built from the project's own dataset, not real usage. Delete
logs/prediction_log.csv afterwards if you want a clean log for real requests.
"""
import argparse
import json
import math
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd  # noqa: E402

from mlops import config as C  # noqa: E402

CONTINUOUS = {"attendance_pct", "avg_internal_marks", "assignment_completion_rate",
              "lms_engagement_score", "previous_semester_score"}


def to_payload(row: pd.Series) -> dict:
    d = {"student_id": str(row["student_id"])}
    for f in C.FEATURES:
        if f.endswith("_data_available"):
            continue  # the API derives these itself
        v = row[f]
        if v is None or (isinstance(v, float) and math.isnan(v)):
            continue
        d[f] = float(v) if f in CONTINUOUS else int(round(float(v)))
    return d


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--drifted", action="store_true", help="use a simulated bad-semester population")
    a = ap.parse_args()

    if a.drifted:
        from mlops.monitoring import simulate_drift
        df = simulate_drift(n=a.n)
    else:
        df = pd.read_csv(C.ML_DATASET_CSV).sample(a.n, random_state=11).reset_index(drop=True)

    payload = [to_payload(r) for _, r in df.iterrows()]
    sent = 0
    for i in range(0, len(payload), 50):
        body = json.dumps({"students": payload[i:i + 50]}).encode()
        req = urllib.request.Request(a.url + "/predict/batch", data=body, headers={"content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            sent += json.loads(r.read())["count"]
    print(f"Sent {sent} {'drifted' if a.drifted else 'normal'} demo predictions to {a.url}")
    print("Now run:  python -m mlops.monitoring")


if __name__ == "__main__":
    main()
