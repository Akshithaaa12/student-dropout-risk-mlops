"""
Streamlit dashboard for the Student Performance & Dropout-Risk
Prediction System (Part 1 -- data & analytics only, no ML model yet).

Run with:
    streamlit run dashboard/app.py

Reads directly from the analytical layer produced by
scripts/run_pipeline.py (db/student_performance.db). If the database
does not exist yet, it tells the user to run the pipeline first instead
of crashing.

Note on the read path: SQLite needs real POSIX file locking, which
cloud-synced or network-mounted project folders (iCloud Drive, OneDrive,
Dropbox, remote dev-environment mounts, etc.) don't always provide --
this can surface as a "disk I/O error" even for a plain read. To be
robust regardless of where this project folder lives, the app copies the
database to a local temp file on every rerun (cheap -- it's a few MB)
and reads from that copy instead of connecting to DB_PATH directly.
"""

import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get("DB_PATH", BASE_DIR / "db" / "student_performance.db"))

st.set_page_config(
    page_title="Student Performance & Dropout-Risk Dashboard",
    layout="wide",
)


def _local_db_copy() -> Path:
    """Copy DB_PATH to a local temp file and return that path (see module
    docstring for why -- avoids SQLite file-locking issues on cloud-synced
    or network-mounted folders)."""
    tmp_path = Path(tempfile.gettempdir()) / "student_performance_dashboard_copy.db"
    shutil.copy2(DB_PATH, tmp_path)
    return tmp_path


@st.cache_data(ttl=30)
def load_table(table_name: str) -> pd.DataFrame:
    local_db = _local_db_copy()
    conn = sqlite3.connect(local_db)
    try:
        return pd.read_sql(f"SELECT * FROM {table_name}", conn)
    finally:
        conn.close()


if not DB_PATH.exists():
    st.error(
        "No database found yet. Run the pipeline first:\n\n"
        "    python scripts/run_pipeline.py"
    )
    st.stop()

mart = load_table("student_performance_mart")
dept_perf = load_table("department_semester_performance")

st.title("🎓 Student Performance & Dropout-Risk Dashboard")
st.caption(
    "Views 1-5 (Part 1, data engineering): risk flags are a transparent "
    "RULE-BASED heuristic (percentile bands on a weighted score), not a trained "
    "ML model. View 6 (Part 2, MLOps) shows the trained model's predicted risk, "
    "its metrics and drift monitoring."
)
_n_imputed = (mart["data_quality_flag"] != "complete").sum()
st.caption(
    f"Missing-data handling: {_n_imputed} of {len(mart)} records had a source with no "
    "record at all (flagged via `data_quality_flag`, then imputed with a documented "
    "fallback) -- see the Student Profile view or docs/validation_rules.md."
)

# ---- Sidebar filters (apply to every view) -----------------------------
st.sidebar.header("Filters")
departments = ["All"] + sorted(mart["department"].unique().tolist())
semesters = ["All"] + sorted(mart["semester"].unique().tolist())
subjects = ["All"] + sorted(mart["subject"].unique().tolist())

sel_dept = st.sidebar.selectbox("Department", departments)
sel_sem = st.sidebar.selectbox("Semester", semesters)
sel_subj = st.sidebar.selectbox("Subject", subjects)

filtered = mart.copy()
if sel_dept != "All":
    filtered = filtered[filtered["department"] == sel_dept]
if sel_sem != "All":
    filtered = filtered[filtered["semester"] == sel_sem]
if sel_subj != "All":
    filtered = filtered[filtered["subject"] == sel_subj]

st.sidebar.metric("Students in view", filtered["student_id"].nunique())

view = st.sidebar.radio(
    "Dashboard view",
    [
        "1. Attendance vs Marks",
        "2. Subject-wise Pass/Fail",
        "3. Department & Semester Performance",
        "4. High-Risk Student List",
        "5. Student Profile & Intervention",
        "6. ML Model: Predicted Risk & Monitoring",
    ],
)

# ---- View 1: Attendance vs Marks ---------------------------------------
if view.startswith("1"):
    st.header("Attendance vs Marks Analysis")
    c1, c2, c3 = st.columns(3)
    c1.metric("Avg attendance %", f"{filtered['attendance_pct'].mean():.1f}%")
    c2.metric("Avg final score (/20)", f"{filtered['current_score'].mean():.1f}")
    c3.metric("Pass rate", f"{filtered['pass_flag'].mean() * 100:.1f}%")

    st.scatter_chart(
        filtered,
        x="attendance_pct",
        y="current_score",
        color="risk_category",
        size=None,
    )
    st.caption(
        "Each point is one student-subject record. Lower attendance "
        "trending with lower final scores is the core early-warning "
        "signal this pipeline is built to surface."
    )
    st.dataframe(
        filtered[["student_id", "department", "semester", "subject",
                  "attendance_pct", "current_score", "risk_category"]]
        .sort_values("attendance_pct"),
        use_container_width=True, height=300,
    )

# ---- View 2: Subject-wise pass/fail -------------------------------------
elif view.startswith("2"):
    st.header("Subject-wise Pass / Fail Distribution")
    subj_grp = (
        filtered.groupby("subject")["pass_flag"]
        .agg(pass_count="sum", total="count")
        .reset_index()
    )
    subj_grp["fail_count"] = subj_grp["total"] - subj_grp["pass_count"]
    subj_grp["pass_rate_pct"] = (subj_grp["pass_count"] / subj_grp["total"] * 100).round(1)

    chart_df = subj_grp.set_index("subject")[["pass_count", "fail_count"]]
    st.bar_chart(chart_df)

    st.dataframe(subj_grp, use_container_width=True)
    st.caption("Pass threshold: final score (G3) >= 10 out of 20, per the UCI dataset's own grading scale.")

# ---- View 3: Department & semester performance --------------------------
elif view.startswith("3"):
    st.header("Department and Semester Performance")
    dgrp = dept_perf.copy()
    if sel_dept != "All":
        dgrp = dgrp[dgrp["department"] == sel_dept]
    if sel_sem != "All":
        dgrp = dgrp[dgrp["semester"] == sel_sem]

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Average final score by department & semester")
        pivot_score = dgrp.pivot_table(index="semester", columns="department", values="avg_score")
        st.bar_chart(pivot_score)
    with col2:
        st.subheader("Pass rate (%) by department & semester")
        pivot_pass = dgrp.pivot_table(index="semester", columns="department", values="pass_rate")
        st.bar_chart(pivot_pass)

    st.dataframe(dgrp.sort_values(["department", "semester"]), use_container_width=True)

# ---- View 4: High-risk student list --------------------------------------
elif view.startswith("4"):
    st.header("High-Risk Student List")
    risk_filter = st.multiselect(
        "Show risk categories", ["High", "Medium", "Low"], default=["High", "Medium"]
    )
    risk_df = filtered[filtered["risk_category"].isin(risk_filter)].sort_values(
        "risk_score", ascending=False
    )
    st.metric("Students flagged", len(risk_df))
    st.dataframe(
        risk_df[["student_id", "department", "semester", "subject",
                 "attendance_pct", "current_score", "assignment_completion_rate",
                 "lms_engagement_score", "risk_score", "risk_category", "data_quality_flag"]],
        use_container_width=True, height=450,
    )
    st.download_button(
        "Download this list as CSV",
        risk_df.to_csv(index=False).encode("utf-8"),
        file_name="high_risk_students.csv",
        mime="text/csv",
    )

# ---- View 5: Student profile & intervention ------------------------------
elif view.startswith("5"):
    st.header("Student Profile & Intervention")
    student_ids = sorted(filtered["student_id"].unique())
    if not student_ids:
        st.warning("No students match the current filters.")
        st.stop()
    sel_student = st.selectbox("Select student ID", student_ids)

    srows = mart[mart["student_id"] == sel_student]
    st.subheader(f"Profile: {sel_student}")

    for _, row in srows.iterrows():
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Subject", row["subject"])
            c2.metric("Attendance %", f"{row['attendance_pct']:.1f}%")
            c3.metric("Final score (/20)", f"{row['current_score']:.1f}")
            c4.metric("Risk", row["risk_category"])

            st.write(
                f"Previous-semester score: **{row['previous_semester_score']:.1f}** | "
                f"Assignment completion: **{row['assignment_completion_rate'] * 100:.0f}%** | "
                f"LMS engagement score: **{row['lms_engagement_score']:.1f}/100**"
            )

            if row["data_quality_flag"] == "complete":
                st.caption("Data completeness: attendance ✅ · LMS ✅ · assignments ✅ (all sources present)")
            else:
                missing = row["data_quality_flag"].replace("imputed:", "")
                st.info(
                    f"⚠️ Data quality: no **{missing}** record was found for this student -- "
                    f"the value shown was imputed (documented fallback), not measured. "
                    f"See docs/validation_rules.md section 5."
                )

            reasons = []
            if row["attendance_pct"] < 75:
                reasons.append("attendance is below the typical 75% eligibility line")
            if row["assignment_completion_rate"] < 0.6:
                reasons.append("assignment completion rate is low")
            if row["lms_engagement_score"] < 40:
                reasons.append("LMS engagement is low")
            if row["current_score"] < 10:
                reasons.append("current score is below the pass mark")

            if row["risk_category"] == "High":
                st.error(
                    "Suggested intervention: schedule a mentor check-in. Key drivers: "
                    + (", ".join(reasons) if reasons else "combination of borderline factors") + "."
                )
            elif row["risk_category"] == "Medium":
                st.warning(
                    "Suggested action: monitor next assessment cycle. Watch: "
                    + (", ".join(reasons) if reasons else "no single dominant factor") + "."
                )
            else:
                st.success("On track -- no intervention flagged.")

# ---- View 6 (Part 2): ML model predictions + monitoring ------------------
elif view.startswith("6"):
    import json
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from mlops import config as C

    st.header("ML Model: Predicted Dropout Risk & Monitoring")
    if not (C.CHAMPION_PATH.exists() and C.ML_DATASET_CSV.exists()):
        st.warning("No trained model yet. Run:  python -m mlops.dataset  &&  python -m mlops.train")
        st.stop()

    import joblib

    meta = json.loads(C.CHAMPION_META.read_text())
    model = joblib.load(C.CHAMPION_PATH)
    op = meta["metrics_test_operating_threshold"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Champion model", meta["algorithm"].replace("_", " "))
    c2.metric("Test ROC-AUC", f"{meta['metrics_test_default_threshold']['roc_auc']:.3f}")
    c3.metric("Recall @ threshold", f"{op['recall']:.0%}")
    c4.metric("Precision @ threshold", f"{op['precision']:.0%}")
    st.caption(
        f"Target: {meta['target_definition']} (a proxy for dropout risk, not literal dropout). "
        f"Registry version {meta.get('registry_version')}, operating threshold {meta['threshold']}. "
        "Predictions are for early-warning conversations, not decisions."
    )

    tab_pred, tab_models, tab_drift = st.tabs(["Predicted risk", "Model comparison", "Drift monitoring"])

    with tab_pred:
        ml = pd.read_csv(C.ML_DATASET_CSV)
        ml["ml_probability"] = model.predict_proba(ml[C.FEATURES])[:, 1]
        ml["ml_flag"] = ml["ml_probability"] >= meta["threshold"]
        view_df = filtered[["student_id", "subject", "risk_category"]].merge(
            ml[["student_id", "ml_probability", "ml_flag", "previous_semester_score", "attendance_pct"]],
            on="student_id", how="inner")
        st.write(f"{int(view_df['ml_flag'].sum())} of {len(view_df)} students in view are flagged at-risk by the model.")
        st.dataframe(view_df.sort_values("ml_probability", ascending=False).head(50), hide_index=True)
        st.caption("Note: the model was trained on 80% of these students, so these in-sample scores look better "
                   "than real performance. Use the held-out test metrics above for honest accuracy.")

    with tab_models:
        cmp_path = C.REPORT_DIR / "model_comparison.csv"
        if cmp_path.exists():
            st.dataframe(pd.read_csv(cmp_path), hide_index=True)
        cols = st.columns(2)
        for col, name in zip(cols, ["roc_curves.png", "shap_summary.png"]):
            if (C.REPORT_DIR / name).exists():
                col.image(str(C.REPORT_DIR / name))

    with tab_drift:
        for fname, title in [("drift_report.json", "Latest check on real API traffic"),
                             ("drift_report_simulated.json", "Simulated drift demo (fabricated shifted batch)")]:
            fp = C.REPORT_DIR / fname
            if not fp.exists():
                continue
            rep = json.loads(fp.read_text())
            st.subheader(title)
            st.write(f"Status: **{rep['status']}** · n={rep['n_current']} · checked {rep['checked_at']}")
            if rep.get("feature_drift"):
                st.dataframe(pd.DataFrame(rep["feature_drift"]).head(8), hide_index=True)
            for t in rep.get("triggers", []):
                st.warning(t)
        if not (C.REPORT_DIR / "drift_report.json").exists():
            st.info("No real-traffic report yet. Send requests to the API, then run: python -m mlops.monitoring")

st.sidebar.divider()
st.sidebar.caption("Data source: UCI Student Performance dataset (primary) + simulated "
                   "attendance/LMS/assignment exports (synthetic, seeded, documented in "
                   "docs/data_dictionary.md).")
