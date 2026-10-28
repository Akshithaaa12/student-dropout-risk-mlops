-- ============================================================================
-- Student Performance & Dropout-Risk Prediction System -- Database Schema
-- Part 1 submission package item 3: "Database schema and sample populated
-- tables". Target engine: SQLite (db/student_performance.db).
--
-- Logical design: a light star schema.
--   dim_student_roster              -- dimension (1 row per student)
--   fact_academic_records            -- fact  (1 row per student x subject)
--   fact_attendance_monthly          -- fact  (1 row per student x semester x month)
--   fact_lms_activity_weekly         -- fact  (1 row per student x week)
--   fact_assignments                 -- fact  (1 row per student x subject x assignment)
--   agg_attendance_student_semester  -- aggregate (1 row per student x semester)
--   agg_lms_student                  -- aggregate (1 row per student)
--   agg_assignment_student_subject   -- aggregate (1 row per student x subject)
--   student_performance_mart         -- ANALYTICAL DATA MART (1 row per student x subject)
--   department_semester_performance  -- rollup (1 row per department x semester)
--
-- NOTE: the pipeline (scripts/transform_load.py) loads these tables via
-- pandas.DataFrame.to_sql(), which does not emit PRIMARY KEY / FOREIGN KEY
-- constraints for a plain SQLite target. The statements below are the
-- documented LOGICAL schema (with keys and types as they are intended to
-- be enforced); they match the physical column layout the pipeline
-- actually creates. If you want the constraints enforced physically, run
-- this file against a fresh sqlite database before running the pipeline,
-- and change transform_load.load_to_sqlite() to use if_exists="append".
-- ============================================================================

-- ---------------------------------------------------------------------------
-- DIMENSION: one row per student (enriched roster: student_id, department,
-- semester are synthetically assigned -- see docs/data_dictionary.md).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_student_roster (
    student_id      TEXT PRIMARY KEY,
    department      TEXT NOT NULL,
    semester        INTEGER NOT NULL,
    academic_year   TEXT NOT NULL,
    source_subject  TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- FACT: raw-ish (post-cleaning) UCI academic record per student x subject.
-- Columns beyond student_id/department/semester/academic_year/
-- source_subject are the original UCI Student Performance attributes.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fact_academic_records (
    student_id      TEXT NOT NULL REFERENCES dim_student_roster(student_id),
    source_subject  TEXT NOT NULL,   -- 'Mathematics' | 'Portuguese'
    department      TEXT NOT NULL,
    semester        INTEGER NOT NULL,
    academic_year   TEXT NOT NULL,
    school TEXT, sex TEXT, age INTEGER, address TEXT, famsize TEXT,
    Pstatus TEXT, Medu INTEGER, Fedu INTEGER, Mjob TEXT, Fjob TEXT,
    reason TEXT, guardian TEXT, traveltime INTEGER, studytime INTEGER,
    failures INTEGER, schoolsup TEXT, famsup TEXT, paid TEXT,
    activities TEXT, nursery TEXT, higher TEXT, internet TEXT,
    romantic TEXT, famrel INTEGER, freetime INTEGER, goout INTEGER,
    Dalc INTEGER, Walc INTEGER, health INTEGER, absences INTEGER,
    G1 INTEGER, G2 INTEGER, G3 INTEGER,
    PRIMARY KEY (student_id, source_subject)
);

-- ---------------------------------------------------------------------------
-- FACT: monthly attendance record per student x semester x month.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fact_attendance_monthly (
    student_id       TEXT NOT NULL REFERENCES dim_student_roster(student_id),
    academic_year    TEXT NOT NULL,
    semester         INTEGER NOT NULL,
    month            TEXT NOT NULL,
    classes_held     INTEGER NOT NULL,
    classes_attended INTEGER NOT NULL,
    PRIMARY KEY (student_id, semester, month)
);

-- ---------------------------------------------------------------------------
-- FACT: weekly LMS (Moodle-style) activity per student x week.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fact_lms_activity_weekly (
    student_id        TEXT NOT NULL REFERENCES dim_student_roster(student_id),
    week              INTEGER NOT NULL,
    logins            INTEGER NOT NULL,
    resources_viewed  INTEGER NOT NULL,
    quiz_attempts     INTEGER NOT NULL,
    quiz_avg_score    REAL NOT NULL,
    forum_posts       INTEGER NOT NULL,
    PRIMARY KEY (student_id, week)
);

-- ---------------------------------------------------------------------------
-- FACT: per-assignment submission record.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fact_assignments (
    student_id      TEXT NOT NULL REFERENCES dim_student_roster(student_id),
    subject         TEXT NOT NULL,
    assignment_no   INTEGER NOT NULL,
    max_marks       INTEGER NOT NULL,
    submitted       INTEGER NOT NULL,   -- boolean (0/1)
    submitted_late  INTEGER NOT NULL,   -- boolean (0/1)
    marks_obtained  REAL,               -- NULL when not submitted
    PRIMARY KEY (student_id, subject, assignment_no)
);

-- ---------------------------------------------------------------------------
-- AGGREGATES (one per source, feeding the mart)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agg_attendance_student_semester (
    student_id       TEXT NOT NULL REFERENCES dim_student_roster(student_id),
    semester         INTEGER NOT NULL,
    classes_held     INTEGER NOT NULL,
    classes_attended INTEGER NOT NULL,
    attendance_pct   REAL NOT NULL,
    PRIMARY KEY (student_id, semester)
);

CREATE TABLE IF NOT EXISTS agg_lms_student (
    student_id            TEXT PRIMARY KEY REFERENCES dim_student_roster(student_id),
    avg_logins_per_week    REAL NOT NULL,
    avg_quiz_score         REAL NOT NULL,
    total_forum_posts      INTEGER NOT NULL,
    lms_engagement_score   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS agg_assignment_student_subject (
    student_id                  TEXT NOT NULL REFERENCES dim_student_roster(student_id),
    subject                     TEXT NOT NULL,
    assignments_total           INTEGER NOT NULL,
    assignments_submitted       INTEGER NOT NULL,
    avg_marks_obtained          REAL,
    assignment_completion_rate  REAL NOT NULL,
    PRIMARY KEY (student_id, subject)
);

-- ---------------------------------------------------------------------------
-- ANALYTICAL DATA MART -- the primary table for the dashboard and the
-- "at least one analytical table or data mart" requirement.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS student_performance_mart (
    student_id                   TEXT NOT NULL REFERENCES dim_student_roster(student_id),
    department                   TEXT NOT NULL,
    semester                     INTEGER NOT NULL,
    subject                      TEXT NOT NULL,
    attendance_pct               REAL NOT NULL,
    avg_internal_marks           REAL NOT NULL,   -- avg(G1, G2)
    previous_semester_score      INTEGER NOT NULL,  -- G2
    current_score                INTEGER NOT NULL,  -- G3
    assignment_completion_rate   REAL NOT NULL,
    lms_engagement_score         REAL NOT NULL,
    pass_flag                    INTEGER NOT NULL,   -- 1 if current_score >= 10
    risk_score                   REAL NOT NULL,       -- rule-based, see data_dictionary.md
    risk_category                TEXT NOT NULL,       -- 'Low' | 'Medium' | 'High'
    attendance_data_available    INTEGER NOT NULL,   -- boolean: False = source had no record at all (see below)
    lms_data_available           INTEGER NOT NULL,   -- boolean
    assignment_data_available    INTEGER NOT NULL,   -- boolean
    data_quality_flag            TEXT NOT NULL,       -- 'complete' | 'imputed:<source[,source...]>'
    PRIMARY KEY (student_id, subject)
);
-- Missing-data policy (see docs/validation_rules.md section 5): a NULL
-- produced by the left-joins that build this mart means one source had
-- NO record at all for that student -- an integration/ingestion gap, not
-- a genuine zero -- and is detected via the *_data_available flags
-- BEFORE attendance_pct/lms_engagement_score/assignment_completion_rate
-- are back-filled with a documented, justified fallback (cohort median
-- for attendance/LMS, 0 for assignment completion). Never silently
-- coerced with no flag.

-- ---------------------------------------------------------------------------
-- ROLLUP: department x semester performance (feeds dashboard view 3).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS department_semester_performance (
    department        TEXT NOT NULL,
    semester           INTEGER NOT NULL,
    n_students          INTEGER NOT NULL,
    avg_score           REAL NOT NULL,
    pass_rate            REAL NOT NULL,   -- percentage 0-100
    avg_attendance       REAL NOT NULL,
    high_risk_count      INTEGER NOT NULL,
    PRIMARY KEY (department, semester)
);
