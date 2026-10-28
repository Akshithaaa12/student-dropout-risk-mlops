"""
transform_load.py -- Transform stage (Cleaned layer -> Analytical layer) + Load into SQLite

Builds:
  * Aggregates: per-student attendance %, LMS engagement, assignment
    completion rate.
  * Feature engineering required by the brief (section 5):
      - attendance percentage
      - average internal marks
      - assignment completion rate
      - previous-semester performance
  * A department/semester rollup for the "Department and semester
    performance" dashboard view.
  * A single analytical data mart (`student_performance_mart`) that is
    the primary source for the dashboard and the required "at least one
    analytical table or data mart".
  * A simple, transparent, RULE-BASED risk score + category (High /
    Medium / Low). This is intentionally NOT a trained ML model --
    Part 1 of the assignment explicitly excludes ML deployment; the
    real predictive model is Part 2's job. This score exists only so
    the "High-risk student list" dashboard view has something
    meaningful to show in Part 1.
  * Explicit missing-data flags (`attendance_data_available`,
    `lms_data_available`, `assignment_data_available`,
    `data_quality_flag`): whenever a source has no record at all for a
    student (an integration gap, not a genuine zero), that gap is
    detected and flagged BEFORE any fallback value is applied -- never
    silently coerced to zero or an unflagged guess. See
    docs/validation_rules.md section 5 for the full policy.

Everything is loaded into a single-file SQLite database
(db/student_performance.db), which the brief allows as "another
approved open-source database".
"""

import os
import sqlite3
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]
CLEAN_DIR = BASE_DIR / "data" / "cleaned"
ANALYTICAL_DIR = BASE_DIR / "data" / "analytical"
# DB location is environment-driven (see .env.example) rather than
# hardcoded, per the brief's "use environment variables for database
# credentials" instruction.
DB_PATH = Path(os.environ.get("DB_PATH", BASE_DIR / "db" / "student_performance.db"))


def build_attendance_agg(attendance: pd.DataFrame) -> pd.DataFrame:
    grp = attendance.groupby(["student_id", "semester"], as_index=False).agg(
        classes_held=("classes_held", "sum"),
        classes_attended=("classes_attended", "sum"),
    )
    grp["attendance_pct"] = (grp["classes_attended"] / grp["classes_held"] * 100).round(1)
    return grp


def build_lms_agg(lms: pd.DataFrame) -> pd.DataFrame:
    grp = lms.groupby("student_id", as_index=False).agg(
        avg_logins_per_week=("logins", "mean"),
        avg_quiz_score=("quiz_avg_score", "mean"),
        total_forum_posts=("forum_posts", "sum"),
    )
    grp["avg_logins_per_week"] = grp["avg_logins_per_week"].round(1)
    grp["avg_quiz_score"] = grp["avg_quiz_score"].round(1)
    # Simple 0-100 engagement score blending logins, quiz score and forum activity.
    grp["lms_engagement_score"] = (
        (grp["avg_logins_per_week"].clip(upper=15) / 15 * 50)
        + (grp["avg_quiz_score"] / 100 * 40)
        + (grp["total_forum_posts"].clip(upper=20) / 20 * 10)
    ).round(1)
    return grp


def build_assignment_agg(assignments: pd.DataFrame) -> pd.DataFrame:
    grp = assignments.groupby(["student_id", "subject"], as_index=False).agg(
        assignments_total=("assignment_no", "count"),
        assignments_submitted=("submitted", "sum"),
        avg_marks_obtained=("marks_obtained", "mean"),
    )
    grp["assignment_completion_rate"] = (
        grp["assignments_submitted"] / grp["assignments_total"]
    ).round(3)
    grp["avg_marks_obtained"] = grp["avg_marks_obtained"].round(1)
    return grp


def build_mart(roster, academic, attendance_agg, lms_agg, assignment_agg) -> pd.DataFrame:
    df = academic.merge(roster[["student_id", "department", "semester"]],
                         on="student_id", suffixes=("", "_roster"))
    df = df.merge(attendance_agg[["student_id", "semester", "attendance_pct"]],
                   on=["student_id", "semester"], how="left")
    df = df.merge(lms_agg[["student_id", "lms_engagement_score"]], on="student_id", how="left")
    df = df.merge(
        assignment_agg[["student_id", "subject", "assignment_completion_rate", "avg_marks_obtained"]],
        left_on=["student_id", "source_subject"], right_on=["student_id", "subject"], how="left",
    )

    df["avg_internal_marks"] = ((df["G1"] + df["G2"]) / 2).round(1)
    df["previous_semester_score"] = df["G2"]
    df["current_score"] = df["G3"]
    df["pass_flag"] = (df["G3"] >= 10).astype(int)

    # ------------------------------------------------------------------
    # Missing-data handling (per docs/validation_rules.md section 5 and
    # the course's missing-data guideline): a NULL after merging sources
    # is NEVER silently coerced to zero or a guessed value without first
    # being detected and flagged. A left-join gap here means one source
    # (attendance / LMS / assignments) had no record at all for this
    # student -- an ingestion/integration gap, not a genuine measurement
    # of zero -- so it is recorded in an explicit *_data_available flag
    # BEFORE any fallback value is applied. The fallback (cohort median
    # for attendance/LMS, 0 for assignment completion) is a documented,
    # justified imputation for downstream usability (the dashboard and
    # Part 2 model need a numeric value), never an unflagged guess.
    # ------------------------------------------------------------------
    df["attendance_data_available"] = df["attendance_pct"].notna()
    df["lms_data_available"] = df["lms_engagement_score"].notna()
    df["assignment_data_available"] = df["assignment_completion_rate"].notna()

    df["attendance_pct"] = df["attendance_pct"].fillna(df["attendance_pct"].median())
    df["assignment_completion_rate"] = df["assignment_completion_rate"].fillna(0)
    df["lms_engagement_score"] = df["lms_engagement_score"].fillna(df["lms_engagement_score"].median())

    def _flag_row(row):
        missing = [
            name for name, ok in (
                ("attendance", row["attendance_data_available"]),
                ("lms", row["lms_data_available"]),
                ("assignment", row["assignment_data_available"]),
            ) if not ok
        ]
        return "complete" if not missing else "imputed:" + ",".join(missing)

    df["data_quality_flag"] = df.apply(_flag_row, axis=1)

    df["risk_score"] = (
        0.4 * (100 - df["attendance_pct"])
        + 0.4 * ((20 - df["current_score"]) / 20 * 100)
        + 0.2 * (100 * (1 - df["assignment_completion_rate"]))
    ).round(1)

    # Risk categories are assigned by PERCENTILE band, not a fixed score
    # cutoff: this is a transparent, rule-based screening heuristic for
    # Part 1 (Part 2 will replace it with a calibrated ML classifier), so
    # thresholds are set relative to this cohort's own score distribution
    # -- top 10% = High, next 20% = Medium, remaining 70% = Low.
    high_cut = df["risk_score"].quantile(0.90)
    medium_cut = df["risk_score"].quantile(0.70)

    def categorize(score):
        if score >= high_cut:
            return "High"
        if score >= medium_cut:
            return "Medium"
        return "Low"

    df["risk_category"] = df["risk_score"].apply(categorize)

    mart_cols = [
        "student_id", "department", "semester", "source_subject",
        "attendance_pct", "avg_internal_marks", "previous_semester_score",
        "current_score", "assignment_completion_rate", "lms_engagement_score",
        "pass_flag", "risk_score", "risk_category",
        "attendance_data_available", "lms_data_available",
        "assignment_data_available", "data_quality_flag",
    ]
    mart = df[mart_cols].rename(columns={"source_subject": "subject"})
    return mart


def build_department_semester_rollup(mart: pd.DataFrame) -> pd.DataFrame:
    grp = mart.groupby(["department", "semester"], as_index=False).agg(
        n_students=("student_id", "nunique"),
        avg_score=("current_score", "mean"),
        pass_rate=("pass_flag", "mean"),
        avg_attendance=("attendance_pct", "mean"),
        high_risk_count=("risk_category", lambda s: (s == "High").sum()),
    )
    for col in ("avg_score", "avg_attendance"):
        grp[col] = grp[col].round(1)
    grp["pass_rate"] = (grp["pass_rate"] * 100).round(1)
    return grp


def load_to_sqlite(tables: dict):
    """Builds the SQLite file in a local temp directory first, then moves
    it into place as a single atomic copy.

    Why: SQLite needs real POSIX file locking for its rollback journal.
    Building it directly on a cloud-synced or network-mounted folder
    (iCloud Drive, OneDrive, Dropbox, or this bridge's own mount) can fail
    with "disk I/O error" mid-write, because those filesystems don't
    reliably support that locking. Writing to a local temp file and then
    copying the finished, closed file into DB_PATH sidesteps the issue
    entirely, regardless of where the project folder happens to live.
    """
    import shutil
    import tempfile

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_db = Path(tmp) / "student_performance.db"
        conn = sqlite3.connect(tmp_db)
        try:
            for name, df in tables.items():
                df.to_sql(name, conn, if_exists="replace", index=False)
            conn.commit()
        finally:
            conn.close()
        shutil.copy2(tmp_db, DB_PATH)


def run():
    roster = pd.read_csv(CLEAN_DIR / "student_roster.csv")
    academic = pd.read_csv(CLEAN_DIR / "academic_records.csv")
    attendance = pd.read_csv(CLEAN_DIR / "attendance.csv")
    lms = pd.read_csv(CLEAN_DIR / "lms_activity.csv")
    assignments = pd.read_csv(CLEAN_DIR / "assignments.csv")

    attendance_agg = build_attendance_agg(attendance)
    lms_agg = build_lms_agg(lms)
    assignment_agg = build_assignment_agg(assignments)
    mart = build_mart(roster, academic, attendance_agg, lms_agg, assignment_agg)
    dept_rollup = build_department_semester_rollup(mart)

    ANALYTICAL_DIR.mkdir(parents=True, exist_ok=True)
    mart.to_csv(ANALYTICAL_DIR / "student_performance_mart.csv", index=False)
    dept_rollup.to_csv(ANALYTICAL_DIR / "department_semester_performance.csv", index=False)
    attendance_agg.to_csv(ANALYTICAL_DIR / "attendance_agg_student_semester.csv", index=False)
    lms_agg.to_csv(ANALYTICAL_DIR / "lms_agg_student.csv", index=False)
    assignment_agg.to_csv(ANALYTICAL_DIR / "assignment_agg_student_subject.csv", index=False)

    load_to_sqlite({
        "dim_student_roster": roster,
        "fact_academic_records": academic,
        "fact_attendance_monthly": attendance,
        "fact_lms_activity_weekly": lms,
        "fact_assignments": assignments,
        "agg_attendance_student_semester": attendance_agg,
        "agg_lms_student": lms_agg,
        "agg_assignment_student_subject": assignment_agg,
        "student_performance_mart": mart,
        "department_semester_performance": dept_rollup,
    })

    print(f"[transform_load] analytical mart rows: {len(mart)}")
    print(f"[transform_load] department/semester rollup rows: {len(dept_rollup)}")
    print(f"[transform_load] loaded {DB_PATH}")
    print(mart["risk_category"].value_counts())
    imputed = (mart["data_quality_flag"] != "complete").sum()
    print(f"[transform_load] records with a flagged, imputed source gap: {imputed} of {len(mart)}")
    if imputed:
        print(mart.loc[mart["data_quality_flag"] != "complete", "data_quality_flag"].value_counts())
    return mart, dept_rollup


if __name__ == "__main__":
    run()
