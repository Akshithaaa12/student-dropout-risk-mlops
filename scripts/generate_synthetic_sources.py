"""
generate_synthetic_sources.py

Builds the supplementary academic-ecosystem data sources that the
UCI Student Performance dataset does not provide on its own:
  - attendance.csv        (simulated ERP attendance export, monthly granularity)
  - lms_activity.csv      (simulated Moodle/LMS activity export, weekly granularity)
  - assignments.csv       (simulated assignment-submission export)

Design notes (documented for the Part 1 report):
  * The UCI dataset (student-mat.csv, student-por.csv) is the PRIMARY,
    real, public historical source (per the assignment brief's suggested use).
  * `student_id`, `department` and `semester` are NOT present in the
    original UCI data. They are synthetically assigned here so the
    pipeline can demonstrate a realistic multi-source, multi-department,
    multi-semester academic warehouse -- this is disclosed in the data
    dictionary as a derived/synthetic field, never presented as real
    student records. No names or other personally identifying
    information are generated anywhere in this project.
  * Attendance, LMS activity and assignment completion are generated
    with a deliberate statistical relationship to each student's real
    UCI attributes (studytime, failures, absences, internet access,
    grades) so that the resulting analytics (attendance vs marks,
    risk flags, etc.) look and behave like a genuine academic dataset
    rather than pure noise.
"""

import numpy as np
import pandas as pd
from pathlib import Path

RNG_SEED = 42
BASE_DIR = Path(__file__).resolve().parents[1]
ACADEMIC_DIR = BASE_DIR / "data" / "source_files" / "academic"
ATTENDANCE_DIR = BASE_DIR / "data" / "source_files" / "attendance"
LMS_DIR = BASE_DIR / "data" / "source_files" / "lms"
ASSIGN_DIR = BASE_DIR / "data" / "source_files" / "assignments"

DEPARTMENTS = ["CSE", "ECE", "MECH", "CIVIL"]
MONTHS = ["Jul", "Aug", "Sep", "Oct"]          # one semester's worth
WEEKS = list(range(1, 13))                      # 12 teaching weeks


def load_academic_sources() -> pd.DataFrame:
    mat = pd.read_csv(ACADEMIC_DIR / "student-mat.csv", sep=";")
    por = pd.read_csv(ACADEMIC_DIR / "student-por.csv", sep=";")
    mat["source_subject"] = "Mathematics"
    por["source_subject"] = "Portuguese"
    combined = pd.concat([mat, por], ignore_index=True)

    rng = np.random.default_rng(RNG_SEED)
    n = len(combined)
    combined.insert(0, "student_id", [f"STU{100000 + i}" for i in range(n)])
    combined["department"] = rng.choice(DEPARTMENTS, size=n)
    combined["semester"] = rng.integers(1, 9, size=n)  # 1..8
    combined["academic_year"] = "2025-26"
    return combined


def make_attendance(students: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(RNG_SEED + 1)
    rows = []
    for _, s in students.iterrows():
        # Base attendance derived from the real 'absences' column (0-93 in source),
        # so the synthetic export is statistically consistent with the source dataset.
        base_pct = np.clip(96 - s["absences"] * 1.6 + rng.normal(0, 4), 35, 100)
        for month in MONTHS:
            classes_held = int(rng.integers(18, 24))
            monthly_pct = np.clip(base_pct + rng.normal(0, 5), 0, 100)
            classes_attended = int(round(classes_held * monthly_pct / 100))
            rows.append({
                "student_id": s["student_id"],
                "academic_year": s["academic_year"],
                "semester": s["semester"],
                "month": month,
                "classes_held": classes_held,
                "classes_attended": min(classes_attended, classes_held),
            })
    return pd.DataFrame(rows)


def make_lms_activity(students: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(RNG_SEED + 2)
    rows = []
    for _, s in students.iterrows():
        has_internet = 1 if s["internet"] == "yes" else 0
        engagement_base = 3 + s["studytime"] * 1.5 + has_internet * 2 - s["failures"] * 1.2
        for week in WEEKS:
            logins = max(0, int(round(rng.normal(engagement_base, 2))))
            rows.append({
                "student_id": s["student_id"],
                "week": week,
                "logins": logins,
                "resources_viewed": max(0, int(round(logins * rng.uniform(0.8, 2.2)))),
                "quiz_attempts": max(0, int(round(rng.normal(engagement_base / 3, 1)))),
                "quiz_avg_score": float(np.clip(rng.normal(50 + s["studytime"] * 5, 15), 0, 100).round(1)),
                "forum_posts": max(0, int(round(rng.poisson(max(engagement_base / 6, 0.1))))),
            })
    return pd.DataFrame(rows)


def make_assignments(students: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(RNG_SEED + 3)
    rows = []
    for _, s in students.iterrows():
        n_assignments = 6
        completion_prob = np.clip(0.55 + s["studytime"] * 0.09 - s["failures"] * 0.12, 0.15, 0.98)
        for a in range(1, n_assignments + 1):
            submitted = rng.random() < completion_prob
            late = submitted and rng.random() < 0.15
            marks = None
            if submitted:
                marks = float(np.clip(rng.normal(60 + s["G1"] * 2, 12), 0, 100).round(1))
            rows.append({
                "student_id": s["student_id"],
                "subject": s["source_subject"],
                "assignment_no": a,
                "max_marks": 100,
                "submitted": bool(submitted),
                "submitted_late": bool(late),
                "marks_obtained": marks,
            })
    return pd.DataFrame(rows)


def main():
    for d in (ATTENDANCE_DIR, LMS_DIR, ASSIGN_DIR):
        d.mkdir(parents=True, exist_ok=True)

    students = load_academic_sources()
    # Persist the enriched roster (student_id/department/semester assignment)
    # alongside the source files so ingestion can treat it as the ERP-style
    # student master export.
    roster_cols = ["student_id", "department", "semester", "academic_year", "source_subject"]
    students.to_csv(ACADEMIC_DIR / "academic_records_enriched.csv", index=False)
    students[roster_cols].to_csv(ACADEMIC_DIR / "student_roster.csv", index=False)

    attendance = make_attendance(students)
    attendance.to_csv(ATTENDANCE_DIR / "attendance_export.csv", index=False)

    lms = make_lms_activity(students)
    lms.to_csv(LMS_DIR / "lms_activity_export.csv", index=False)

    assignments = make_assignments(students)
    assignments.to_csv(ASSIGN_DIR / "assignment_submissions.csv", index=False)

    print(f"Students (rows across both subjects): {len(students)}")
    print(f"Attendance rows: {len(attendance)}")
    print(f"LMS activity rows: {len(lms)}")
    print(f"Assignment rows: {len(assignments)}")


if __name__ == "__main__":
    main()
