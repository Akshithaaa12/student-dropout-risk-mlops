"""
Build the curated ML dataset (Part 2, step 1).

Reads the Part 1 outputs only (analytical mart + cleaned academic records),
creates the supervised target, keeps ONLY the leakage-free feature columns from
mlops/config.py, and writes:
    data/ml/ml_dataset.csv          (flat file, consumed by training/monitoring)
    data/ml/ml_dataset_meta.json    (row counts, class balance, feature list)
    table  ml_training_dataset      (in the SQLite warehouse, next to the mart)

Run:  python -m mlops.dataset
"""

import json
import sqlite3
import sys
from datetime import datetime, timezone

import pandas as pd

from mlops import config as C


def build_dataset() -> pd.DataFrame:
    mart_path = C.ANALYTICAL_DIR / "student_performance_mart.csv"
    acad_path = C.CLEAN_DIR / "academic_records.csv"
    for p in (mart_path, acad_path):
        if not p.exists():
            sys.exit(f"Missing {p}. Run the Part 1 pipeline first: python scripts/run_pipeline.py")

    mart = pd.read_csv(mart_path)
    acad = pd.read_csv(acad_path)

    keep_acad = ["student_id", "G3", "sex", "source_subject", "studytime", "failures",
                 "absences", "goout", "Dalc", "Walc", "freetime", "health", "famrel",
                 "Medu", "Fedu", "age", "traveltime", "internet", "higher",
                 "schoolsup", "famsup", "paid", "activities", "romantic"]
    df = mart.merge(acad[keep_acad], on="student_id", how="inner", validate="one_to_one")

    # --- encode binaries -----------------------------------------------------
    for col in ["internet", "higher", "schoolsup", "famsup", "paid", "activities", "romantic"]:
        df[col] = (df[col].astype(str).str.lower() == "yes").astype(int)
    df["is_male"] = (df["sex"] == "M").astype(int)
    df["is_math"] = (df["source_subject"] == "Mathematics").astype(int)
    for col in C.FLAG_FEATURES:
        df[col] = df[col].astype(str).str.lower().isin(["true", "1"]).astype(int)

    # --- target (G3 comes from the cleaned record, used ONLY to make the label) --
    df[C.TARGET] = (df["G3"] < C.PASS_MARK).astype(int)

    out = df[["student_id"] + C.FEATURES + [C.TARGET]].copy()
    assert out["student_id"].is_unique
    assert not set(C.FEATURES) & {"G3", "current_score", "pass_flag", "risk_score", "risk_category"}, "leakage!"
    return out


def main() -> None:
    C.ML_DIR.mkdir(parents=True, exist_ok=True)
    df = build_dataset()
    df.to_csv(C.ML_DATASET_CSV, index=False)

    meta = {
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rows": int(len(df)),
        "target": C.TARGET,
        "target_definition": f"1 if final score G3 < {C.PASS_MARK} (on course to fail) else 0",
        "positive_rate": round(float(df[C.TARGET].mean()), 4),
        "n_features": len(C.FEATURES),
        "features": C.FEATURES,
        "null_cells": int(df.isna().sum().sum()),
    }
    C.ML_DATASET_META.write_text(json.dumps(meta, indent=2))

    # also land it in the warehouse next to the mart (local temp copy trick is
    # handled by transform_load for the big write; this table is tiny)
    try:
        con = sqlite3.connect(C.DB_PATH)
        df.to_sql("ml_training_dataset", con, if_exists="replace", index=False)
        con.close()
        wrote_db = True
    except sqlite3.Error as exc:  # synced folders sometimes reject SQLite writes
        wrote_db = False
        print(f"[warn] could not write ml_training_dataset to SQLite ({exc}); CSV is still written.")

    print(f"ML dataset: {len(df)} rows x {len(C.FEATURES)} features | at-risk rate {meta['positive_rate']:.1%} "
          f"| db table written: {wrote_db}")


if __name__ == "__main__":
    main()
