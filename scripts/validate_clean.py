"""
validate_clean.py -- Validation & Cleaning stage (Raw layer -> Cleaned layer)

Implements the ETL / data-engineering requirements from the brief
(section 5):
  * Standardize student identifiers across sources.
  * Remove duplicates and invalid marks.
  * Handle missing attendance and assignment records.

Every row that is dropped or corrected is written to
logs/rejected_records.csv with a reason code, so the rejection log the
brief asks for ("data-quality checks and ... rejected-record or error
log") is fully auditable. See docs/validation_rules.md for the rules
in plain language.
"""

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = BASE_DIR / "data" / "raw"
CLEAN_DIR = BASE_DIR / "data" / "cleaned"
LOG_DIR = BASE_DIR / "logs"
REJECTED_LOG = LOG_DIR / "rejected_records.csv"

VALID_GRADE_MIN, VALID_GRADE_MAX = 0, 20

_rejected_rows = []


def _reject(table: str, row: pd.Series, reason: str):
    rec = row.to_dict()
    rec["_rejected_from_table"] = table
    rec["_rejection_reason"] = reason
    rec["_rejected_at"] = datetime.now(timezone.utc).isoformat()
    _rejected_rows.append(rec)


def _standardize_id(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.upper()


def clean_roster() -> pd.DataFrame:
    df = pd.read_csv(RAW_DIR / "raw_student_roster.csv")
    df["student_id"] = _standardize_id(df["student_id"])

    dupes = df[df.duplicated(subset=["student_id"], keep="first")]
    for _, row in dupes.iterrows():
        _reject("student_roster", row, "duplicate_student_id")
    df = df.drop_duplicates(subset=["student_id"], keep="first").reset_index(drop=True)

    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(CLEAN_DIR / "student_roster.csv", index=False)
    return df


def clean_academic(valid_ids: set) -> pd.DataFrame:
    df = pd.read_csv(RAW_DIR / "raw_academic_records.csv")
    df["student_id"] = _standardize_id(df["student_id"])

    # Duplicate (student_id, source_subject) pairs
    dupe_mask = df.duplicated(subset=["student_id", "source_subject"], keep="first")
    for _, row in df[dupe_mask].iterrows():
        _reject("academic_records", row, "duplicate_student_subject")
    df = df[~dupe_mask]

    # Invalid marks: UCI grades must be within 0-20
    invalid_mask = ~df["G3"].between(VALID_GRADE_MIN, VALID_GRADE_MAX)
    for _, row in df[invalid_mask].iterrows():
        _reject("academic_records", row, f"G3_out_of_range(0-{VALID_GRADE_MAX})")
    df = df[~invalid_mask]

    # Referential integrity: student must exist in roster
    orphan_mask = ~df["student_id"].isin(valid_ids)
    for _, row in df[orphan_mask].iterrows():
        _reject("academic_records", row, "student_id_not_in_roster")
    df = df[~orphan_mask]

    df = df.reset_index(drop=True)
    df.to_csv(CLEAN_DIR / "academic_records.csv", index=False)
    return df


def clean_attendance(valid_ids: set) -> pd.DataFrame:
    df = pd.read_csv(RAW_DIR / "raw_attendance.csv")
    df["student_id"] = _standardize_id(df["student_id"])

    orphan_mask = ~df["student_id"].isin(valid_ids)
    for _, row in df[orphan_mask].iterrows():
        _reject("attendance", row, "student_id_not_in_roster")
    df = df[~orphan_mask]

    dupe_mask = df.duplicated(subset=["student_id", "semester", "month"], keep="first")
    for _, row in df[dupe_mask].iterrows():
        _reject("attendance", row, "duplicate_month_record")
    df = df[~dupe_mask]

    invalid_mask = df["classes_attended"] > df["classes_held"]
    for _, row in df[invalid_mask].iterrows():
        _reject("attendance", row, "attended_exceeds_held")
    df = df[~invalid_mask]

    df = df.reset_index(drop=True)
    df.to_csv(CLEAN_DIR / "attendance.csv", index=False)

    # Missing-record completeness log (not a rejection -- an information
    # gap): which students are missing which expected months.
    expected_months = {"Jul", "Aug", "Sep", "Oct"}
    present = df.groupby("student_id")["month"].apply(set)
    completeness = present.apply(lambda months: sorted(expected_months - months))
    missing_df = completeness[completeness.apply(len) > 0].reset_index()
    missing_df.columns = ["student_id", "missing_months"]
    missing_df.to_csv(LOG_DIR / "attendance_completeness_gaps.csv", index=False)

    return df


def clean_lms(valid_ids: set) -> pd.DataFrame:
    df = pd.read_csv(RAW_DIR / "raw_lms_activity.csv")
    df["student_id"] = _standardize_id(df["student_id"])
    orphan_mask = ~df["student_id"].isin(valid_ids)
    for _, row in df[orphan_mask].iterrows():
        _reject("lms_activity", row, "student_id_not_in_roster")
    df = df[~orphan_mask].reset_index(drop=True)
    df.to_csv(CLEAN_DIR / "lms_activity.csv", index=False)
    return df


def clean_assignments(valid_ids: set) -> pd.DataFrame:
    df = pd.read_csv(RAW_DIR / "raw_assignments.csv")
    df["student_id"] = _standardize_id(df["student_id"])
    orphan_mask = ~df["student_id"].isin(valid_ids)
    for _, row in df[orphan_mask].iterrows():
        _reject("assignments", row, "student_id_not_in_roster")
    df = df[~orphan_mask].reset_index(drop=True)
    # Missing marks_obtained where submitted=False is expected, not an error.
    df.to_csv(CLEAN_DIR / "assignments.csv", index=False)
    return df


def run():
    global _rejected_rows
    _rejected_rows = []

    roster = clean_roster()
    valid_ids = set(roster["student_id"])

    academic = clean_academic(valid_ids)
    attendance = clean_attendance(valid_ids)
    lms = clean_lms(valid_ids)
    assignments = clean_assignments(valid_ids)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if _rejected_rows:
        pd.DataFrame(_rejected_rows).to_csv(REJECTED_LOG, index=False)
    else:
        pd.DataFrame(columns=["_rejected_from_table", "_rejection_reason"]).to_csv(REJECTED_LOG, index=False)

    summary = {
        "student_roster": len(roster),
        "academic_records": len(academic),
        "attendance": len(attendance),
        "lms_activity": len(lms),
        "assignments": len(assignments),
        "rejected_total": len(_rejected_rows),
    }
    print("[validate_clean] cleaned row counts:")
    for k, v in summary.items():
        print(f"  {k:16s}: {v}")
    print(f"[validate_clean] rejected-record log -> {REJECTED_LOG}")
    return summary


if __name__ == "__main__":
    run()
