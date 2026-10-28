"""
Drift monitoring + retraining decision (Part 2, step 3).

Compares what the API has actually been scoring (logs/prediction_log.csv) with the
training-time reference snapshot (models/reference_stats.json).

    python -m mlops.monitoring                  # check the real prediction log
    python -m mlops.monitoring --simulate-drift # DEMO: fabricate a shifted batch (clearly labelled)
    python -m mlops.monitoring --retrain        # if triggers fire, run mlops.train

Checks
  * data drift        PSI per feature (>0.10 watch, >0.25 drift) + KS test for continuous features
  * prediction drift  share flagged at-risk vs the training positive rate
  * missing data      share of requests with each *_data_available flag = 0
  * performance       recall / ROC-AUC on logged students whose true outcome is known
                      (data/ml/outcomes.csv: student_id, at_risk_actual) - skipped if absent

Retraining policy (docs/monitoring_policy.md)
  T1  >= 2 features with PSI > 0.20, or any feature with PSI > 0.25
  T2  flagged share moved > 10 percentage points from the training rate
  T3  recall < 0.70 or ROC-AUC dropped > 0.05 (needs outcomes)
  T4  model older than 180 days (one academic semester)
"""

import argparse
import json
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy import stats

from mlops import config as C

PSI_WATCH, PSI_DRIFT, PSI_SEVERE = 0.10, 0.20, 0.25
MIN_ROWS = 30  # below this a drift check is mostly noise
EPS = 1e-4


def psi(ref_share, cur_share) -> float:
    r = np.clip(np.asarray(ref_share, float), EPS, None)
    c = np.clip(np.asarray(cur_share, float), EPS, None)
    return float(np.sum((c - r) * np.log(c / r)))


def feature_psi(ref: dict, values: pd.Series) -> float:
    v = values.dropna().astype(float)
    if ref["kind"] == "continuous":
        edges = np.array(ref["edges"])
        # open-ended outer bins so out-of-range values still count
        counts, _ = np.histogram(np.clip(v, edges[0], edges[-1]), bins=edges)
        share = counts / max(counts.sum(), 1)
    else:
        share = np.array([(v == x).mean() for x in ref["values"]])
        other = 1 - share.sum()
        if other > 0.001:  # unseen category -> extra bin
            return psi(list(ref["share"]) + [EPS], list(share) + [other])
    return psi(ref["share"], share)


def label(p: float) -> str:
    return "drift" if p > PSI_SEVERE else ("warning" if p > PSI_DRIFT else ("watch" if p > PSI_WATCH else "stable"))


def simulate_drift(n=200, seed=7) -> pd.DataFrame:
    """DEMO ONLY. Take real students and push the population the way a bad semester would:
    lower attendance/engagement, weaker scores, more absences. Marked in the report."""
    rng = np.random.default_rng(seed)
    df = pd.read_csv(C.ML_DATASET_CSV).sample(n, replace=True, random_state=seed).reset_index(drop=True)
    df["attendance_pct"] = np.clip(df["attendance_pct"] - rng.normal(14, 4, n), 20, 100)
    df["lms_engagement_score"] = np.clip(df["lms_engagement_score"] - rng.normal(18, 5, n), 0, 100)
    df["previous_semester_score"] = np.clip(df["previous_semester_score"] - rng.normal(2.2, 1, n), 0, 20).round()
    df["avg_internal_marks"] = np.clip(df["avg_internal_marks"] - rng.normal(2.0, 0.8, n), 0, 20)
    df["absences"] = (df["absences"] + rng.poisson(5, n)).astype(int)
    return df


def score_frame(df: pd.DataFrame) -> pd.DataFrame:
    import joblib
    model = joblib.load(C.CHAMPION_PATH)
    meta = json.loads(C.CHAMPION_META.read_text())
    out = df.copy()
    out["probability"] = model.predict_proba(out[C.FEATURES])[:, 1]
    out["at_risk"] = (out["probability"] >= meta["threshold"]).astype(int)
    return out


def run(simulated=False, log_to_mlflow=True) -> dict:
    ref = json.loads(C.REFERENCE_STATS.read_text())
    meta = json.loads(C.CHAMPION_META.read_text())

    if simulated:
        cur = score_frame(simulate_drift())
        source = "SIMULATED shifted batch (demo, not real traffic)"
    else:
        if not C.PREDICTION_LOG.exists():
            sys.exit("No prediction log yet. Send requests to the API (or use --simulate-drift for a demo).")
        cur = pd.read_csv(C.PREDICTION_LOG)
        source = str(C.PREDICTION_LOG.name)

    n = len(cur)
    report = {"checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "source": source, "simulated": simulated, "n_current": n,
              "n_reference": ref["n_rows"], "model_version": meta.get("registry_version"),
              "algorithm": meta.get("algorithm")}
    if n < MIN_ROWS:
        report.update(status="insufficient_data", triggers=[],
                      message=f"Only {n} logged predictions; need >= {MIN_ROWS} for a meaningful check.")
        return report

    # --- data drift -------------------------------------------------------------
    rows = []
    for f, r in ref["features"].items():
        p = feature_psi(r, cur[f])
        row = {"feature": f, "psi": round(p, 4), "status": label(p),
               "ref_mean": round(r["mean"], 3), "cur_mean": round(float(cur[f].mean()), 3)}
        if r["kind"] == "continuous":
            ks = stats.ks_2samp(r["sample"], cur[f].dropna())
            row["ks_stat"], row["ks_p"] = round(float(ks.statistic), 4), round(float(ks.pvalue), 6)
        rows.append(row)
    drift_df = pd.DataFrame(rows).sort_values("psi", ascending=False)
    report["feature_drift"] = drift_df.astype(object).where(drift_df.notna(), None).to_dict("records")  # NaN -> null (strict JSON)

    # --- prediction drift ----------------------------------------------------------
    flagged = float(cur["at_risk"].mean())
    ref_rate = float(meta["metrics_test_operating_threshold"]["tp"] + meta["metrics_test_operating_threshold"]["fp"])
    ref_rate /= (meta["metrics_test_operating_threshold"]["tp"] + meta["metrics_test_operating_threshold"]["fp"]
                 + meta["metrics_test_operating_threshold"]["tn"] + meta["metrics_test_operating_threshold"]["fn"])
    report["prediction_drift"] = {"flagged_share_current": round(flagged, 4),
                                  "flagged_share_reference": round(ref_rate, 4),
                                  "shift_pp": round((flagged - ref_rate) * 100, 2)}

    # --- missing data -----------------------------------------------------------------
    report["missing_data"] = {c: round(float(1 - cur[c].mean()), 4) for c in C.FLAG_FEATURES}

    # --- performance (only when ground truth is known) --------------------------------
    perf = None
    outcomes = C.ML_DIR / "outcomes.csv"
    if outcomes.exists() and "student_id" in cur.columns:
        from sklearn.metrics import recall_score, roc_auc_score
        j = cur.merge(pd.read_csv(outcomes), on="student_id", how="inner")
        if len(j) >= MIN_ROWS and j["at_risk_actual"].nunique() == 2:
            perf = {"n_labelled": int(len(j)),
                    "recall": round(float(recall_score(j["at_risk_actual"], j["at_risk"])), 4),
                    "roc_auc": round(float(roc_auc_score(j["at_risk_actual"], j["probability"])), 4)}
    report["performance"] = perf or "not evaluated (no labelled outcomes yet)"

    # --- retraining triggers --------------------------------------------------------------
    trig = []
    n_over = int((drift_df["psi"] > PSI_DRIFT).sum())
    worst = drift_df.iloc[0]
    if n_over >= 2 or worst["psi"] > PSI_SEVERE:
        trig.append(f"T1 data drift: {n_over} feature(s) PSI>{PSI_DRIFT} (worst {worst['feature']} = {worst['psi']})")
    if abs(report["prediction_drift"]["shift_pp"]) > 10:
        trig.append(f"T2 prediction drift: flagged share moved {report['prediction_drift']['shift_pp']:+.1f} pp")
    if perf and (perf["recall"] < 0.70 or perf["roc_auc"] < meta["metrics_test_default_threshold"]["roc_auc"] - 0.05):
        trig.append(f"T3 performance decay: recall {perf['recall']}, AUC {perf['roc_auc']}")
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(meta["trained_at"])).days
    report["model_age_days"] = age
    if age > 180:
        trig.append(f"T4 model age {age} days > 180")
    report["triggers"] = trig
    report["status"] = "RETRAIN_RECOMMENDED" if trig else "healthy"

    # --- persist --------------------------------------------------------------------------
    C.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    name = "drift_report_simulated" if simulated else "drift_report"
    (C.REPORT_DIR / f"{name}.json").write_text(json.dumps(report, indent=2, allow_nan=False))
    drift_df.to_csv(C.REPORT_DIR / f"{name}_features.csv", index=False)
    if log_to_mlflow:
        try:
            import mlflow
            from mlops import tracking
            tracking.setup(C.MONITORING_EXPERIMENT)
            with mlflow.start_run(run_name=name + datetime.now().strftime("-%Y%m%d-%H%M%S")):
                mlflow.set_tags({"simulated": str(simulated), "status": report["status"]})
                mlflow.log_metrics({"n_current": n, "max_psi": float(worst["psi"]),
                                    "features_over_0.2": n_over,
                                    "flagged_share": flagged, "flagged_shift_pp": report["prediction_drift"]["shift_pp"]})
                mlflow.log_artifact(str(C.REPORT_DIR / f"{name}.json"))
        except Exception as exc:  # monitoring must not fail because tracking is down
            report["mlflow_warning"] = str(exc)
    return report


def print_report(r: dict) -> None:
    print(f"\n=== Drift report | {r['source']} | n={r['n_current']} | model v{r.get('model_version')} ({r.get('algorithm')}) ===")
    if r["status"] == "insufficient_data":
        print(r["message"]); return
    print("Top drifting features (PSI):")
    for d in r["feature_drift"][:6]:
        print(f"  {d['feature']:28s} PSI {d['psi']:6.3f}  [{d['status']}]  mean {d['ref_mean']} -> {d['cur_mean']}")
    pdft = r["prediction_drift"]
    print(f"Flagged at-risk: {pdft['flagged_share_current']:.1%} now vs {pdft['flagged_share_reference']:.1%} reference ({pdft['shift_pp']:+.1f} pp)")
    print(f"Performance: {r['performance']}")
    print(f"STATUS: {r['status']}")
    for t in r["triggers"]:
        print("  -", t)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--simulate-drift", action="store_true")
    ap.add_argument("--retrain", action="store_true", help="run training if a trigger fires")
    ap.add_argument("--no-mlflow", action="store_true")
    a = ap.parse_args()
    rep = run(simulated=a.simulate_drift, log_to_mlflow=not a.no_mlflow)
    print_report(rep)
    if a.retrain and rep.get("triggers"):
        from mlops import train
        print("\nTriggers fired -> retraining ...")
        train.main(register=True)
