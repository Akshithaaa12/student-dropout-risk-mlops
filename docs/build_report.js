// Build docs/report.docx -- the Part 1 project report.
// Run with: node docs/build_report.js   (from the project root)
// Requires the `docx` npm package (dev-only build tool; not needed to
// read or submit the generated report.docx itself).

const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle,
  ImageRun, PageBreak, Header, Footer, PageNumber, NumberFormat,
  LevelFormat, convertInchesToTwip,
} = require("docx");

const ROOT = path.resolve(__dirname, "..");
const img = (p) => fs.readFileSync(path.join(ROOT, p));

// ---------- small helpers -------------------------------------------------
const H1 = (text) => new Paragraph({ text, heading: HeadingLevel.HEADING_1, spacing: { before: 300, after: 150 } });
const H2 = (text) => new Paragraph({ text, heading: HeadingLevel.HEADING_2, spacing: { before: 200, after: 100 } });
const P = (text, opts = {}) => new Paragraph({ children: [new TextRun({ text, ...opts })], spacing: { after: 120 } });
const Bold = (text) => new TextRun({ text, bold: true });
const bullet = (text) => new Paragraph({ text, bullet: { level: 0 }, spacing: { after: 60 } });
const pageBreak = () => new Paragraph({ children: [new PageBreak()] });

function cell(text, { width, bold = false, shade = null, align = AlignmentType.LEFT } = {}) {
  return new TableCell({
    width: { size: width, type: WidthType.DXA },
    shading: shade ? { type: ShadingType.CLEAR, fill: shade } : undefined,
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    children: [new Paragraph({ alignment: align, children: [new TextRun({ text: String(text), bold })] })],
  });
}

function simpleTable(headers, rows, widths) {
  const total = widths.reduce((a, b) => a + b, 0);
  return new Table({
    width: { size: total, type: WidthType.DXA },
    columnWidths: widths,
    rows: [
      new TableRow({ children: headers.map((h, i) => cell(h, { width: widths[i], bold: true, shade: "D9E2F3" })) }),
      ...rows.map((r) => new TableRow({ children: r.map((v, i) => cell(v, { width: widths[i] })) })),
    ],
  });
}

function figure(imgPath, widthPx, heightPx, caption) {
  return [
    new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new ImageRun({ data: img(imgPath), transformation: { width: widthPx, height: heightPx }, type: "png" })],
    }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 }, children: [new TextRun({ text: caption, italics: true, size: 18 })] }),
  ];
}

// ---------- content -------------------------------------------------------

const titlePage = [
  new Paragraph({ text: "", spacing: { before: 1600 } }),
  new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "PROJECT 1", size: 24, color: "666666" })] }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 200, after: 200 },
    children: [new TextRun({ text: "Student Performance and Dropout-Risk Prediction System", bold: true, size: 40 })],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 400 },
    children: [new TextRun({ text: "Part 1 -- Data Pipeline Implementation: Project Report", size: 28, color: "444444" })],
  }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 }, children: [new TextRun({ text: "Course: Data Engineering and MLOps", size: 22 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 }, children: [new TextRun({ text: "Mode: Individual Project", size: 22 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 }, children: [new TextRun({ text: "Submitted by: Akshitha", size: 22 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 400 }, children: [new TextRun({ text: "Submission date: 7 September 2026", size: 22 })] }),
  pageBreak(),
];

const sec1 = [
  H1("1. Introduction & Background"),
  P(
    "Academic institutions generate a continuous stream of data about their students -- attendance registers, " +
    "internal assessment marks, assignment submissions, and, increasingly, learning-management-system (LMS) " +
    "activity logs. In practice this data lives in separate systems that are rarely joined together, so early " +
    "signs that a student is struggling (falling attendance, missed assignments, declining marks, low LMS " +
    "engagement) are often visible only in hindsight, after a student has already fallen behind."
  ),
  P(
    "This project builds a data-engineering pipeline that unifies these sources into a single, clean, " +
    "queryable academic-analytics warehouse, and exposes it through an interactive dashboard so that patterns " +
    "-- attendance vs. marks, subject-wise pass/fail rates, department- and semester-level performance, and a " +
    "high-risk student list -- are visible immediately rather than after the fact. Part 1 of the assignment " +
    "(this report) covers the data engineering half of the system end-to-end: acquisition, ingestion, " +
    "validation/cleaning, storage, transformation, and visualization. Part 2, to be announced separately, will " +
    "extend this same pipeline with a trained machine-learning model, MLflow experiment tracking, FastAPI " +
    "serving, Docker containerization, and drift monitoring."
  ),
  H2("1.1 Justification"),
  P(
    "A rule-based or ML-based early-warning system is only as good as the data pipeline feeding it. Building a " +
    "disciplined, layered pipeline (source -> raw -> cleaned -> analytical) with explicit validation rules and " +
    "an auditable rejected-record log is what makes the eventual Part 2 model trustworthy: every feature the " +
    "model will consume in Part 2 (attendance percentage, average internal marks, assignment completion rate, " +
    "previous-semester performance) is already defined, computed, and documented here in Part 1."
  ),
];

const sec2 = [
  H1("2. Project Objectives & Scope"),
  H2("2.1 Objectives (from the assignment brief)"),
  bullet("Create a unified student data pipeline from multiple academic sources."),
  bullet("Clean, validate, transform, and store student records in a structured database."),
  bullet("Develop dashboards for performance, attendance, and risk analysis."),
  bullet("Extend the pipeline into an MLOps workflow for dropout/performance-risk prediction (Part 2)."),
  H2("2.2 Part 1 scope (this report)"),
  P("Part 1 is explicitly limited to data engineering -- no ML model is trained or deployed at this stage. Delivered in Part 1:"),
  bullet("Dataset acquisition and documentation (Section 3)."),
  bullet("A four-layer data architecture: source -> raw -> cleaned -> analytical (Section 4)."),
  bullet("Ingestion scripts with extraction logging (Section 5.1)."),
  bullet("Validation and cleaning with a rejected-record log (Section 5.2)."),
  bullet("Feature engineering and a SQLite analytical data mart (Section 6)."),
  bullet("A 5-view Streamlit dashboard, including a transparent rule-based risk flag (Section 7)."),
  bullet("Full documentation: architecture diagram, data dictionary, validation rules, schema, README."),
  H2("2.3 Role of ML in this system (and why Part 1 has none)"),
  P(
    "The eventual role of machine learning (Part 2) is to replace the simple, transparent, rule-based " +
    "risk_score computed in this pipeline (Section 7.3) with a trained classifier -- starting with Logistic " +
    "Regression as an interpretable baseline, then Random Forest and XGBoost for improved accuracy -- predicting " +
    "one of dropout risk, failure risk, or a final-score category, tracked with MLflow and served via FastAPI. " +
    "Part 1 deliberately stops short of this so that the data foundation can be evaluated on its own merits " +
    "first."
  ),
];

const sec3 = [
  H1("3. Data Sources"),
  P(
    "Per the assignment's dataset rule (“use only free, legally accessible, public, institutional, or " +
    "instructor-approved datasets”), this project combines one real public dataset with simulated " +
    "supplementary sources. Full access instructions are in docs/data_sources.md; summarized below."
  ),
  simpleTable(
    ["Source", "Type", "Rows", "Role"],
    [
      ["UCI Student Performance dataset (student-mat.csv, student-por.csv)", "Real, public (CC BY 4.0)", "395 + 649 = 1,044", "Primary historical dataset"],
      ["College ERP roster export", "Simulated (seeded)", "1,044 (+dup noise)", "student_id / department / semester enrichment"],
      ["ERP attendance export", "Simulated (seeded, linked to real 'absences')", "4,176 (-noise)", "Monthly attendance -> attendance %"],
      ["LMS activity export", "Simulated (seeded, linked to studytime/internet)", "12,528", "Weekly engagement -> LMS engagement score"],
      ["Assignment submissions export", "Simulated (seeded, linked to studytime/failures)", "6,264", "Per-assignment marks -> completion rate"],
    ],
    [3800, 2100, 1300, 2800],
  ),
  new Paragraph({ text: "", spacing: { after: 150 } }),
  P(
    "The UCI dataset (P. Cortez & A. Silva, 2008; UCI ML Repository, dataset id 320) was retrieved via a " +
    "public GitHub mirror of the identical, unmodified CSV files, since the UCI archive host itself was not " +
    "reachable from the network used to build this pipeline; values were spot-checked against the documented " +
    "UCI schema (33 columns, 0-20 grade scale) after download. No real student names, government IDs, or other " +
    "personally identifiable information appear anywhere in this project -- every student is identified only by " +
    "a synthetic student_id, per the brief's explicit prohibition on private/confidential data."
  ),
  H2("3.1 Why simulate attendance, LMS and assignment data?"),
  P(
    "The brief lists ERP and LMS exports as optional institutional sources. As an individual student project " +
    "without access to a real college ERP/LMS feed -- and forbidden from uploading real institutional records -- " +
    "these three sources were generated synthetically with deliberate, documented statistical relationships to " +
    "the real UCI attributes (e.g., simulated attendance is derived from each student's real absences value; " +
    "LMS engagement scales with real studytime and internet-access fields), so the resulting pipeline and " +
    "dashboard behave like a genuine multi-source academic dataset rather than being populated with arbitrary " +
    "random noise. This design choice, and its limitations, are disclosed in full in docs/data_dictionary.md."
  ),
];

const sec4 = [
  H1("4. System / Data Architecture"),
  P(
    "The pipeline follows the layered architecture suggested by the brief (CSV/ERP/LMS -> Python ingestion -> " +
    "orchestration -> validation & cleaning -> warehouse -> analytics tables -> dashboard), implemented exactly " +
    "as shown below."
  ),
  ...figure("docs/architecture_diagram.png", 620, 195, "Figure 1. End-to-end pipeline architecture (source -> raw -> cleaned -> analytical -> dashboard)."),
  H2("4.1 Layers"),
  simpleTable(
    ["Layer", "Location", "Produced by"],
    [
      ["Source", "data/source_files/", "External (UCI download + generate_synthetic_sources.py)"],
      ["Raw", "data/raw/", "scripts/ingest.py"],
      ["Cleaned", "data/cleaned/", "scripts/validate_clean.py"],
      ["Analytical", "data/analytical/ + db/student_performance.db", "scripts/transform_load.py"],
    ],
    [2200, 3800, 3500],
  ),
];

const sec5 = [
  H1("5. ETL / Data Engineering Implementation"),
  H2("5.1 Ingestion (scripts/ingest.py)"),
  P("Extracts each of the five source files into the raw layer, and for every source logs the extraction timestamp, source name, target raw file, status, and row count to logs/extraction_log.csv:"),
  simpleTable(
    ["Source", "Raw file", "Status", "Rows"],
    [
      ["college_erp_roster", "raw_student_roster.csv", "SUCCESS", "1,059"],
      ["uci_academic_records", "raw_academic_records.csv", "SUCCESS", "1,054"],
      ["erp_attendance_export", "raw_attendance.csv", "SUCCESS", "4,093"],
      ["lms_activity_export", "raw_lms_activity.csv", "SUCCESS", "12,528"],
      ["assignment_submissions_export", "raw_assignments.csv", "SUCCESS", "6,264"],
    ],
    [3600, 3200, 1600, 1900],
  ),
  new Paragraph({ text: "", spacing: { after: 150 } }),
  P(
    "To make the downstream validation stage demonstrate genuine data-quality work, ingestion deliberately " +
    "injects a small, seeded amount of realistic noise while copying into the raw layer (duplicate roster/" +
    "academic rows, a few out-of-range grades, a handful of missing attendance rows) -- fully documented in " +
    "ingest.py's docstring and docs/validation_rules.md. The original UCI source files are never altered."
  ),
  H2("5.2 Validation & Cleaning (scripts/validate_clean.py)"),
  P("Implements: identifier standardization, duplicate removal, invalid-mark rejection, referential-integrity checks, and missing-record handling. Every dropped/corrected row is logged with a reason code:"),
  simpleTable(
    ["Rejection reason", "Count"],
    [
      ["duplicate_student_id (roster)", "15"],
      ["duplicate_student_subject (academic)", "10"],
      ["G3_out_of_range (0-20 scale)", "10"],
      ["Total rejected", "35"],
    ],
    [5500, 2000],
  ),
  new Paragraph({ text: "", spacing: { after: 150 } }),
  P("Full rule descriptions are in docs/validation_rules.md; the raw rejected rows themselves are in logs/rejected_records.csv."),
  H2("5.3 Orchestration"),
  P(
    "scripts/run_pipeline.py runs ingestion -> validation/cleaning -> transformation/load as a single, " +
    "re-runnable command, logging each stage's status and timing to logs/pipeline_run_log.txt. " +
    "dags/student_pipeline_dag.py defines the identical three-stage task graph as a real Apache Airflow DAG " +
    "(PythonOperator tasks, ingest_task >> validate_task >> transform_load_task), satisfying the brief's " +
    "“Airflow DAG, or an approved equivalent ETL workflow” requirement; run_pipeline.py is what is used " +
    "for the live demo to avoid depending on a freshly-installed Airflow scheduler being available on demand."
  ),
  H2("5.4 Missing-Data Handling"),
  P(
    "Guiding principle: a NULL produced anywhere in this pipeline is never automatically replaced by zero or " +
    "a guessed value. The cause is identified first, and the treatment depends on that cause and on how the " +
    "feature will be used -- distinguishing a genuine measurement from a data-quality gap."
  ),
  simpleTable(
    ["Situation", "Where", "Handling"],
    [
      ["Partial gap -- a student has some but not all expected attendance months", "validate_clean.py", "Not fabricated: attendance % computed from months present; gap logged to attendance_completeness_gaps.csv"],
      ["Full gap -- a source has no record at all for a student that semester", "transform_load.py (mart)", "Flagged FIRST (attendance_data_available / lms_data_available / assignment_data_available = False), THEN a documented fallback (cohort median, or 0 for assignments) is applied"],
      ["Missing assignment marks (not submitted)", "source data", "Kept NULL, never coerced to 0 -- a meaningful absence, directly lowers assignment_completion_rate"],
    ],
    [3800, 1900, 3600],
  ),
  new Paragraph({ text: "", spacing: { after: 150 } }),
  P(
    "The mart carries this as an explicit, auditable column (data_quality_flag: \"complete\" or " +
    "\"imputed:<source>\"), rather than an invisible substitution. In the current seeded run, 15 of 1,034 " +
    "student-subject records are flagged imputed:attendance -- a genuine case produced by simulating a " +
    "full-semester ERP sync failure for a small subset of students (see ingest.py)."
  ),
  ...figure("screenshots/06_missing_data_flag.png", 580, 326, "Figure 5. Student Profile view surfacing a flagged, imputed record (student STU100041 had no attendance source record for this semester)."),
];

const sec6 = [
  H1("6. Database Schema & Data Dictionary"),
  P(
    "All cleaned and analytical tables are loaded into a single-file SQLite warehouse " +
    "(db/student_performance.db) -- an approved open-source database per the brief. The design is a light star " +
    "schema: one dimension table (dim_student_roster), four fact tables at their natural grain, three " +
    "per-student aggregates, one analytical data mart, and one department/semester rollup. Full DDL is in " +
    "docs/schema.sql; the complete column-level data dictionary (with real vs. synthetic vs. derived " +
    "provenance for every field) is in docs/data_dictionary.md. Key tables:"
  ),
  simpleTable(
    ["Table", "Grain", "Rows"],
    [
      ["dim_student_roster", "1 per student", "1,044"],
      ["fact_academic_records", "1 per student x subject", "1,034"],
      ["fact_attendance_monthly", "1 per student x semester x month", "4,093"],
      ["fact_lms_activity_weekly", "1 per student x week", "12,528"],
      ["fact_assignments", "1 per student x subject x assignment", "6,264"],
      ["student_performance_mart (data mart)", "1 per student x subject", "1,034"],
      ["department_semester_performance", "1 per department x semester", "32"],
    ],
    [4200, 3600, 1700],
  ),
];

const sec7 = [
  H1("7. Feature Engineering & Risk Scoring"),
  P("scripts/transform_load.py computes every feature the brief requires, all landing in student_performance_mart:"),
  simpleTable(
    ["Required feature", "Definition"],
    [
      ["Attendance percentage", "classes_attended / classes_held x 100, aggregated per student per semester"],
      ["Average internal marks", "(G1 + G2) / 2 (period-1 and period-2 UCI grades)"],
      ["Assignment completion rate", "assignments_submitted / assignments_total, per student per subject"],
      ["Previous-semester performance", "G2 (the UCI dataset's second-period grade)"],
    ],
    [3200, 6300],
  ),
  new Paragraph({ text: "", spacing: { after: 150 } }),
  H2("7.1 A supplementary engagement signal"),
  P("lms_engagement_score (0-100) blends weekly logins (50%), average quiz score (40%) and forum posts (10%) into a single number, giving the dashboard an LMS-derived signal beyond the four required features."),
  H2("7.2 Rule-based risk score (Part 1 only -- not an ML model)"),
  P("risk_score = 0.4 x (100 - attendance_pct) + 0.4 x ((20 - current_score) / 20 x 100) + 0.2 x (100 x (1 - assignment_completion_rate))"),
  P(
    "Students are then bucketed into Low / Medium / High risk_category by PERCENTILE band within the current " +
    "cohort (top 10% -> High, next 20% -> Medium, remaining 70% -> Low), rather than a fixed score cutoff, so " +
    "the thresholds stay meaningful regardless of dataset size. This is intentionally a transparent, auditable " +
    "heuristic -- Part 2 will replace it with a trained, evaluated classifier."
  ),
  simpleTable(
    ["Risk category", "Students (of 1,034)", "Share"],
    [
      ["Low", "722", "69.8%"],
      ["Medium", "207", "20.0%"],
      ["High", "105", "10.2%"],
    ],
    [2500, 3200, 1800],
  ),
  new Paragraph({ text: "", spacing: { after: 150 } }),
  P(
    "Cohort-level result: overall pass rate 77.9% (G3 >= 10) and average attendance 88.6% across all 1,034 " +
    "student-subject records after cleaning."
  ),
];

const sec8 = [
  H1("8. Dashboard & Visualization"),
  P(
    "dashboard/app.py is a Streamlit application reading directly from the SQLite warehouse, with sidebar " +
    "filters (department, semester, subject) that apply across all five required views."
  ),
  ...figure("screenshots/01_attendance_vs_marks.png", 600, 375, "Figure 2. View 1 -- Attendance vs. Marks Analysis (scatter, coloured by risk category)."),
  pageBreak(),
  ...figure("screenshots/03_department_semester.png", 600, 375, "Figure 3. View 3 -- Department and Semester Performance (average score and pass rate)."),
  ...figure("screenshots/04_high_risk_list.png", 600, 375, "Figure 4. View 4 -- High-Risk Student List (filterable, downloadable as CSV)."),
  P("The remaining two required views -- Subject-wise Pass/Fail Distribution and Student Profile & Intervention (with a rule-based, plain-language intervention suggestion per student) -- are included in the live application and in screenshots/02_subject_pass_fail.png and screenshots/05_student_profile.png."),
];

const sec9 = [
  H1("9. Execution Evidence"),
  P("A full pipeline run (python scripts/run_pipeline.py) completes all three stages successfully in well under one second on this dataset size, producing the following log artefacts (all included in this submission):"),
  bullet("logs/extraction_log.csv -- per-source extraction status and row counts (Section 5.1)."),
  bullet("logs/rejected_records.csv -- 35 rejected rows with reason codes (Section 5.2)."),
  bullet("logs/attendance_completeness_gaps.csv -- students with missing monthly attendance records."),
  bullet("logs/pipeline_run_log.txt -- timestamped STAGE START / STAGE OK lines for the full run."),
  bullet("db/student_performance.db -- the populated 10-table SQLite warehouse."),
  bullet("screenshots/ -- five dashboard-view screenshots captured from a live run of the application."),
  P("Additional terminal-output screenshots from the live review demo should be added to screenshots/ alongside these before final submission."),
];

const sec10 = [
  H1("10. Conclusion & Part 2 Roadmap"),
  P(
    "This Part 1 submission delivers a complete, working, documented data pipeline: a real public dataset " +
    "combined with realistic supplementary sources, ingested with logging, validated and cleaned with a full " +
    "audit trail, transformed into an engineered feature set and loaded into a queryable SQLite warehouse, and " +
    "surfaced through a 5-view interactive dashboard -- with no shortcuts taken on the parts of the brief that " +
    "are explicitly graded (rejected-record logging, data dictionary, architecture diagram, orchestration)."
  ),
  P(
    "Part 2 will build directly on this foundation: the four engineered features already computed here " +
    "(attendance percentage, average internal marks, assignment completion rate, previous-semester performance) " +
    "become the model's input features; the rule-based risk_category becomes the baseline to beat; and " +
    "student_performance_mart becomes the training table for a Logistic Regression baseline followed by Random " +
    "Forest and XGBoost, tracked in MLflow, served via FastAPI, containerized with Docker, and monitored for " +
    "input drift -- exactly as specified in Section 8 of the assignment brief."
  ),
];

const doc = new Document({
  numbering: {
    config: [{ reference: "bullet-list", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT }] }],
  },
  sections: [
    {
      properties: { page: { size: { width: 11906, height: 16838 } } }, // A4
      headers: {
        default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: "Student Performance & Dropout-Risk Prediction System -- Part 1", size: 16, color: "888888" })] })] }),
      },
      footers: {
        default: new Footer({
          children: [new Paragraph({
            alignment: AlignmentType.CENTER,
            children: [new TextRun({ children: [PageNumber.CURRENT], size: 18 })],
          })],
        }),
      },
      children: [
        ...titlePage,
        ...sec1, ...sec2, pageBreak(),
        ...sec3, pageBreak(),
        ...sec4, pageBreak(),
        ...sec5, pageBreak(),
        ...sec6, pageBreak(),
        ...sec7, pageBreak(),
        ...sec8, pageBreak(),
        ...sec9, pageBreak(),
        ...sec10,
      ],
    },
  ],
});

Packer.toBuffer(doc).then((buf) => {
  const out = path.join(ROOT, "docs", "report.docx");
  fs.writeFileSync(out, buf);
  console.log("Wrote", out);
});
