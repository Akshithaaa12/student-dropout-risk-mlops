"""
Single source of truth for Part 2 paths, constants and the feature contract.

The FEATURE contract is the most important thing in here: it is shared by
training (mlops/train.py), serving (api/main.py), monitoring
(mlops/monitoring.py) and the dashboard, so a feature can never be "known"
to one component and silently missing from another.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]

# ---- Locations --------------------------------------------------------------
ANALYTICAL_DIR = BASE_DIR / "data" / "analytical"
CLEAN_DIR = BASE_DIR / "data" / "cleaned"
ML_DIR = BASE_DIR / "data" / "ml"
MODEL_DIR = BASE_DIR / "models"
REPORT_DIR = BASE_DIR / "reports"
LOG_DIR = BASE_DIR / "logs"
DB_PATH = Path(os.environ.get("DB_PATH", BASE_DIR / "db" / "student_performance.db"))

ML_DATASET_CSV = ML_DIR / "ml_dataset.csv"
ML_DATASET_META = ML_DIR / "ml_dataset_meta.json"
CHAMPION_PATH = MODEL_DIR / "champion.joblib"
CHAMPION_META = MODEL_DIR / "champion_meta.json"
REFERENCE_STATS = MODEL_DIR / "reference_stats.json"
PREDICTION_LOG = LOG_DIR / "prediction_log.csv"

# ---- MLflow -----------------------------------------------------------------
# SQLite-backed store (needed for the Model Registry). Override with
# MLFLOW_TRACKING_URI to point at a remote server such as DagsHub:
#   MLFLOW_TRACKING_URI=https://dagshub.com/<user>/<repo>.mlflow
#   MLFLOW_TRACKING_USERNAME=<user>   MLFLOW_TRACKING_PASSWORD=<token>
MLSTORE_DIR = Path(os.environ.get("MLSTORE_DIR", BASE_DIR / "mlstore"))
MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", f"sqlite:///{MLSTORE_DIR / 'mlflow.db'}")
MLFLOW_EXPERIMENT = os.environ.get("MLFLOW_EXPERIMENT", "student-dropout-risk")
MONITORING_EXPERIMENT = "student-dropout-risk-monitoring"
REGISTERED_MODEL_NAME = os.environ.get("REGISTERED_MODEL_NAME", "student-dropout-risk")
CHAMPION_ALIAS = "champion"

RANDOM_SEED = 42
TEST_SIZE = 0.20
CV_FOLDS = 5

# ---- Problem definition -----------------------------------------------------
# The UCI data has no literal "dropped out" column, so the supervised target is
# a transparent proxy: the student's FINAL score (G3, 0-20 scale) is below the
# dataset's own pass mark of 10. "At risk" therefore means "on course to fail the
# subject", which is the early-warning signal an advisor would act on.
PASS_MARK = 10
TARGET = "at_risk"

# ---- Feature contract -------------------------------------------------------
# Predictions are made at MID-semester: after the second assessment period (G2)
# but BEFORE the final result (G3). Everything below is knowable at that time.
#
# DELIBERATELY EXCLUDED (see docs/ml_design.md):
#   current_score / G3 / pass_flag / risk_score / risk_category -> target leakage
#       (the rule-based Part 1 risk_score is computed FROM the final score).
#   department / semester -> synthetic random enrichments with no real signal.
#   student_id -> identifier, not a feature.
NUMERIC_FEATURES = [
    # from the analytical mart (multi-source: ERP attendance, LMS, assignments, grades)
    "attendance_pct",
    "avg_internal_marks",
    "previous_semester_score",
    "assignment_completion_rate",
    "lms_engagement_score",
    # from the real UCI academic record
    "studytime", "failures", "absences", "goout", "Dalc", "Walc",
    "freetime", "health", "famrel", "Medu", "Fedu", "age", "traveltime",
]
BINARY_FEATURES = [
    "internet", "higher", "schoolsup", "famsup", "paid", "activities", "romantic",
    "is_male", "is_math",
]
# Missing-data flags from Part 1 (course guideline): 1 = the source HAD a record.
FLAG_FEATURES = [
    "attendance_data_available", "lms_data_available", "assignment_data_available",
]
FEATURES = NUMERIC_FEATURES + BINARY_FEATURES + FLAG_FEATURES

# Plain-language labels used by the dashboard / API explanations.
FEATURE_LABELS = {
    "attendance_pct": "Attendance %",
    "avg_internal_marks": "Average internal marks",
    "previous_semester_score": "Previous-period score (G2)",
    "assignment_completion_rate": "Assignment completion rate",
    "lms_engagement_score": "LMS engagement score",
    "studytime": "Weekly study time (1-4)",
    "failures": "Past class failures",
    "absences": "School absences",
    "goout": "Going out with friends (1-5)",
    "Dalc": "Workday alcohol use (1-5)",
    "Walc": "Weekend alcohol use (1-5)",
    "freetime": "Free time after school (1-5)",
    "health": "Health status (1-5)",
    "famrel": "Family relationship quality (1-5)",
    "Medu": "Mother's education (0-4)",
    "Fedu": "Father's education (0-4)",
    "age": "Age",
    "traveltime": "Home-to-school travel time (1-4)",
    "internet": "Has internet at home",
    "higher": "Wants higher education",
    "schoolsup": "Extra school support",
    "famsup": "Family educational support",
    "paid": "Paid extra classes",
    "activities": "Extracurricular activities",
    "romantic": "In a relationship",
    "is_male": "Male",
    "is_math": "Subject is Mathematics",
    "attendance_data_available": "Attendance record present",
    "lms_data_available": "LMS record present",
    "assignment_data_available": "Assignment record present",
}

# Sanity ranges used by the API validators and the monitoring data-quality checks.
FEATURE_RANGES = {
    "attendance_pct": (0, 100), "avg_internal_marks": (0, 20),
    "previous_semester_score": (0, 20), "assignment_completion_rate": (0, 1),
    "lms_engagement_score": (0, 100), "studytime": (1, 4), "failures": (0, 4),
    "absences": (0, 100), "goout": (1, 5), "Dalc": (1, 5), "Walc": (1, 5),
    "freetime": (1, 5), "health": (1, 5), "famrel": (1, 5), "Medu": (0, 4),
    "Fedu": (0, 4), "age": (14, 30), "traveltime": (1, 4),
}
