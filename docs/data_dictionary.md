# Data Dictionary

Database: `db/student_performance.db` (SQLite). Full DDL: `docs/schema.sql`.
Provenance key used below: **R** = real UCI data, **S** = synthetically
generated for this project (seeded, reproducible), **D** = derived by the
pipeline (aggregation / feature engineering).

## dim_student_roster
One row per student.

| Column | Type | Provenance | Description |
|---|---|---|---|
| student_id | TEXT (PK) | S | Synthetic anonymized identifier assigned during enrichment (`STU1000xx`). No real names/PII are used anywhere in this project. |
| department | TEXT | S | Synthetically assigned (CSE/ECE/MECH/CIVIL) -- the UCI source has no department field; added to demonstrate department-level analytics. |
| semester | INTEGER | S | Synthetically assigned, 1-8. |
| academic_year | TEXT | S | Fixed value "2025-26" for this run. |
| source_subject | TEXT | R | Which UCI file the student's academic record came from: "Mathematics" or "Portuguese". |

## fact_academic_records
One row per (student_id, source_subject). All columns other than the
join/enrichment keys are the **original, unmodified UCI Student
Performance attributes** (real data) -- see `docs/data_sources.md` for
the full UCI attribute glossary. Selected columns used downstream:

| Column | Type | Provenance | Description |
|---|---|---|---|
| studytime | INTEGER (1-4) | R | Weekly study time band. |
| failures | INTEGER | R | Number of past class failures. |
| absences | INTEGER | R | School absences recorded in the source dataset. |
| internet | TEXT (yes/no) | R | Home internet access. |
| G1, G2, G3 | INTEGER (0-20) | R | Period-1, period-2, and final grades. Used as previous-semester and current-semester performance signals. |

## fact_attendance_monthly
One row per (student_id, semester, month). **S** -- simulated ERP-style
monthly attendance export, generated with a statistical link to each
student's real `absences` value (see `scripts/generate_synthetic_sources.py`)
so it behaves like a genuine attendance feed rather than pure noise.

| Column | Type | Description |
|---|---|---|
| classes_held | INTEGER | Classes scheduled that month. |
| classes_attended | INTEGER | Classes the student attended. |

## fact_lms_activity_weekly
One row per (student_id, week). **S** -- simulated Moodle-style LMS
export, correlated with `studytime`, `internet` access and `failures`.

| Column | Type | Description |
|---|---|---|
| logins | INTEGER | LMS logins that week. |
| resources_viewed | INTEGER | Course resources opened. |
| quiz_attempts | INTEGER | Practice quiz attempts. |
| quiz_avg_score | REAL (0-100) | Average quiz score that week. |
| forum_posts | INTEGER | Discussion forum posts. |

## fact_assignments
One row per (student_id, subject, assignment_no). **S** -- simulated
assignment-submission export, correlated with `studytime` and `failures`.

| Column | Type | Description |
|---|---|---|
| submitted | INTEGER (bool) | Whether the assignment was submitted. |
| submitted_late | INTEGER (bool) | Whether it was submitted late. |
| marks_obtained | REAL, nullable | NULL when not submitted (expected, not an error). |

## agg_attendance_student_semester / agg_lms_student / agg_assignment_student_subject
**D** -- per-student(-semester) aggregates computed by
`scripts/transform_load.py` (mean/sum roll-ups of the fact tables above).
`attendance_pct = classes_attended / classes_held * 100`.
`lms_engagement_score` blends logins (50%), quiz score (40%) and forum
activity (10%) onto a 0-100 scale.
`assignment_completion_rate = assignments_submitted / assignments_total`.

## student_performance_mart  (the analytical data mart)
**D** -- one row per (student_id, subject). This is the primary table the
dashboard reads.

| Column | Type | Description |
|---|---|---|
| attendance_pct | REAL | See above. **Required feature: attendance percentage.** |
| avg_internal_marks | REAL | `(G1 + G2) / 2`. **Required feature: average internal marks.** |
| previous_semester_score | INTEGER | `G2`. **Required feature: previous-semester performance.** |
| current_score | INTEGER | `G3`, this semester's final grade. |
| assignment_completion_rate | REAL (0-1) | See above. **Required feature: assignment completion rate.** |
| lms_engagement_score | REAL (0-100) | See above (supplementary engagement signal). |
| pass_flag | INTEGER (bool) | 1 if `current_score >= 10` (UCI's own pass mark on a 0-20 scale). |
| risk_score | REAL | `0.4*(100-attendance_pct) + 0.4*((20-current_score)/20*100) + 0.2*(100*(1-assignment_completion_rate))`. A transparent, **rule-based** weighted heuristic -- **not** a trained ML model. Higher = more at-risk. |
| risk_category | TEXT | `Low` / `Medium` / `Low` assigned by **percentile band** within the current cohort: top 10% of `risk_score` -> High, next 20% -> Medium, remaining 70% -> Low. Thresholds are relative, not fixed, so they stay meaningful as the dataset grows. Part 2 will replace this heuristic with a trained classifier. |
| attendance_data_available | INTEGER (bool) | `False` when the attendance source had **no record at all** for this student's semester (e.g. a simulated ERP sync failure) -- an integration gap, not a genuine 0% attendance. See "Missing-data policy" below. |
| lms_data_available | INTEGER (bool) | Same idea, for the LMS source. |
| assignment_data_available | INTEGER (bool) | Same idea, for the assignment-submissions source. |
| data_quality_flag | TEXT | `"complete"` if all three sources had a record, otherwise `"imputed:<source[,source...]>"` naming exactly which source(s) were missing and had to be back-filled. Human-readable summary of the three flags above. |

### Missing-data policy (why these flag columns exist)
A NULL produced when building this mart (i.e. a left-join found no
matching row in the attendance/LMS/assignment aggregate for a given
student) is **never silently replaced with zero or a guessed value**.
`scripts/transform_load.py` first records the fact that data was
missing (`*_data_available = False`, `data_quality_flag` names the
source), and only THEN applies a documented fallback so the dashboard
and any future model always receive a numeric value:
- `attendance_pct` / `lms_engagement_score` -> cohort median for that run.
- `assignment_completion_rate` -> 0 (no submission evidence exists).

This distinguishes a genuine measurement (a student who truly attended
0% of classes) from a data-quality gap (the source never sent a record),
and makes every imputed value traceable rather than indistinguishable
from real data -- see docs/validation_rules.md section 5 for the full
policy and the exact injected failure mode that produces these cases.

## department_semester_performance
**D** -- one row per (department, semester): `n_students`, `avg_score`,
`pass_rate` (%), `avg_attendance`, `high_risk_count`. Feeds dashboard view 3.

## Known limitations (disclose in the report)
- `department` and `semester` are synthetic enrichments, not present in
  the original UCI dataset -- necessary to demonstrate multi-department,
  multi-semester analytics, but not real institutional assignments.
- Attendance, LMS activity and assignment data are simulated (seeded,
  reproducible), standing in for a real ERP/LMS export per the brief's
  allowance for "instructor-approved" / representative datasets when a
  live institutional feed isn't available. The statistical relationships
  they carry (e.g., attendance vs. absences, engagement vs. studytime)
  are designed to be realistic, not arbitrary.
- `risk_score` / `risk_category` are intentionally simple and rule-based;
  they exist only to give the Part 1 dashboard something to show for the
  "high-risk student list" view. The actual predictive model is Part 2's
  deliverable.
