"""
ingest.py -- Ingestion stage (Source layer -> Raw layer)

Responsibilities (per assignment brief, section 5 "Minimum ingestion
expectations"):
  * Maintain a raw copy of the extracted data (untouched, one file per source).
  * Record extraction date, source, file/API status, and row count.
  * Handle extraction errors and log failed records.
  * Support a repeatable / re-runnable ingestion workflow.

This script is deliberately import-friendly (a single `run()` entry point)
so it can be called directly, from run_pipeline.py, or wrapped by an
Airflow PythonOperator (see dags/student_pipeline_dag.py).

Note on "dirty" raw data: real ERP/LMS/CSV exports are never perfectly
clean. To make the downstream validation stage (validate_clean.py)
demonstrate real data-quality work -- as the brief requires ("remove
duplicates and invalid marks", "handle missing attendance and assignment
records") -- this stage injects a small, seeded, clearly-documented amount
of realistic noise (duplicate rows, out-of-range marks, missing rows)
while copying source files into the raw layer. This mirrors how a real
extraction from an ERP/LMS would arrive imperfect; nothing here alters
the original UCI source files themselves, which remain untouched in
data/source_files/.
"""

import shutil
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
SOURCE_DIR = BASE_DIR / "data" / "source_files"
RAW_DIR = BASE_DIR / "data" / "raw"
LOG_DIR = BASE_DIR / "logs"
EXTRACTION_LOG = LOG_DIR / "extraction_log.csv"

NOISE_SEED = 7


def _log_extraction(rows):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    header = not EXTRACTION_LOG.exists()
    df.to_csv(EXTRACTION_LOG, mode="a", header=header, index=False)


def _inject_noise_roster(df: pd.DataFrame) -> pd.DataFrame:
    """Simulate realistic ERP roster extraction issues."""
    rng = np.random.default_rng(NOISE_SEED)
    df = df.copy()
    # Duplicate ~1.5% of rows (simulates ERP sync re-sending records)
    dup_idx = rng.choice(df.index, size=max(1, int(len(df) * 0.015)), replace=False)
    df = pd.concat([df, df.loc[dup_idx]], ignore_index=True)
    return df


def _inject_noise_academic(df: pd.DataFrame) -> pd.DataFrame:
    """Simulate realistic marks-extraction issues on the academic source."""
    rng = np.random.default_rng(NOISE_SEED + 1)
    df = df.copy()
    n = len(df)
    # Invalid / out-of-range marks (~1%): UCI grades are 0-20.
    bad_idx = rng.choice(df.index, size=max(1, int(n * 0.01)), replace=False)
    for i in bad_idx:
        df.loc[i, "G3"] = int(rng.choice([-1, 25, 99]))
    # Duplicate a few rows (ERP re-extraction overlap)
    dup_idx = rng.choice(df.index, size=max(1, int(n * 0.01)), replace=False)
    df = pd.concat([df, df.loc[dup_idx]], ignore_index=True)
    return df


def _inject_noise_attendance(df: pd.DataFrame) -> pd.DataFrame:
    """Simulate two distinct, realistic attendance-extraction failure modes:

    1. Scattered single-month gaps (~2% of rows) -- e.g. one month's
       upload from the ERP was skipped for an otherwise-tracked student.
       validate_clean.py logs these as partial completeness gaps, and
       transform_load.py computes attendance % from whichever months
       remain (a genuinely partial record, not missing entirely).

    2. A full-semester sync failure for a small set of students (~1.5%
       of student-semester pairs) -- e.g. the ERP never sent that
       student's attendance batch at all for that semester. This is
       what produces a real, demonstrable
       `attendance_data_available = False` case downstream in the
       analytical mart, rather than leaving the missing-data flagging
       logic with nothing to show in a live demo.
    """
    rng = np.random.default_rng(NOISE_SEED + 2)

    # 1. Scattered single-month gaps.
    drop_idx = rng.choice(df.index, size=max(1, int(len(df) * 0.02)), replace=False)
    df = df.drop(index=drop_idx).reset_index(drop=True)

    # 2. Full-semester sync failures for a handful of student-semester pairs.
    pairs = df[["student_id", "semester"]].drop_duplicates().reset_index(drop=True)
    n_fail = max(1, int(len(pairs) * 0.015))
    fail_idx = rng.choice(pairs.index, size=n_fail, replace=False)
    fail_pairs = set(map(tuple, pairs.loc[fail_idx].values))
    keep_mask = ~df.apply(lambda r: (r["student_id"], r["semester"]) in fail_pairs, axis=1)
    df = df[keep_mask].reset_index(drop=True)

    return df


def _extract_one(source_name, src_path: Path, raw_name: str, noise_fn=None):
    status = "SUCCESS"
    row_count = 0
    error_msg = ""
    try:
        df = pd.read_csv(src_path)
        if noise_fn is not None:
            df = noise_fn(df)
        row_count = len(df)
        RAW_DIR.mkdir(parents=True, exist_ok=True)
        df.to_csv(RAW_DIR / raw_name, index=False)
    except Exception as exc:  # pragma: no cover - defensive logging path
        status = "FAILED"
        error_msg = str(exc)
    return {
        "extraction_timestamp": datetime.now(timezone.utc).isoformat(),
        "source_name": source_name,
        "source_file": str(src_path.relative_to(BASE_DIR)),
        "raw_file": raw_name,
        "status": status,
        "row_count": row_count,
        "error_message": error_msg,
    }


def run():
    log_rows = []

    log_rows.append(_extract_one(
        "college_erp_roster", SOURCE_DIR / "academic" / "student_roster.csv",
        "raw_student_roster.csv", noise_fn=_inject_noise_roster,
    ))
    log_rows.append(_extract_one(
        "uci_academic_records", SOURCE_DIR / "academic" / "academic_records_enriched.csv",
        "raw_academic_records.csv", noise_fn=_inject_noise_academic,
    ))
    log_rows.append(_extract_one(
        "erp_attendance_export", SOURCE_DIR / "attendance" / "attendance_export.csv",
        "raw_attendance.csv", noise_fn=_inject_noise_attendance,
    ))
    log_rows.append(_extract_one(
        "lms_activity_export", SOURCE_DIR / "lms" / "lms_activity_export.csv",
        "raw_lms_activity.csv",
    ))
    log_rows.append(_extract_one(
        "assignment_submissions_export", SOURCE_DIR / "assignments" / "assignment_submissions.csv",
        "raw_assignments.csv",
    ))

    _log_extraction(log_rows)

    failed = [r for r in log_rows if r["status"] != "SUCCESS"]
    for r in log_rows:
        print(f"[ingest] {r['source_name']:28s} -> {r['raw_file']:28s} "
              f"status={r['status']:8s} rows={r['row_count']}")
    if failed:
        print(f"[ingest] WARNING: {len(failed)} source(s) failed extraction. See {EXTRACTION_LOG}")
    return log_rows


if __name__ == "__main__":
    run()
