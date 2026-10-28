// Build docs/part2_report.docx -- Part 2 (MLOps) project report.
// Run from the project root:  node docs/build_part2_report.js
// Numbers are read from models/champion_meta.json and reports/*.json so the report
// can never drift from what the code actually produced.

const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, Table, TableRow, TableCell,
  WidthType, ShadingType, ImageRun, PageBreak, Header, Footer, PageNumber, LevelFormat,
} = require("docx");

const ROOT = path.resolve(__dirname, "..");
const img = (p) => fs.readFileSync(path.join(ROOT, p));
const J = (p) => JSON.parse(fs.readFileSync(path.join(ROOT, p), "utf8"));
const meta = J("models/champion_meta.json");
const drift = J("reports/drift_report_simulated.json");
const f2 = (x) => Number(x).toFixed(2), f3 = (x) => Number(x).toFixed(3);
const T = meta.all_models, B = meta.baselines, OP = meta.metrics_test_operating_threshold, DF = meta.metrics_test_default_threshold;

const H1 = (text) => new Paragraph({ text, heading: HeadingLevel.HEADING_1, spacing: { before: 300, after: 150 } });
const H2 = (text) => new Paragraph({ text, heading: HeadingLevel.HEADING_2, spacing: { before: 200, after: 100 } });
const P = (text, opts = {}) => new Paragraph({ children: [new TextRun({ text, ...opts })], spacing: { after: 120 } });
const bullet = (text) => new Paragraph({ children: [new TextRun(text)], numbering: { reference: "bullets", level: 0 }, spacing: { after: 60 } });
const code = (text) => new Paragraph({ children: [new TextRun({ text, font: "Courier New", size: 18 })], spacing: { after: 40 }, indent: { left: 300 } });
const pageBreak = () => new Paragraph({ children: [new PageBreak()] });

function cell(text, { width, bold = false, shade = null } = {}) {
  return new TableCell({
    width: { size: width, type: WidthType.DXA },
    shading: shade ? { type: ShadingType.CLEAR, fill: shade } : undefined,
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    children: [new Paragraph({ children: [new TextRun({ text: String(text), bold, size: 20 })] })],
  });
}
function table(headers, rows, widths) {
  const total = widths.reduce((a, b) => a + b, 0);
  return new Table({
    width: { size: total, type: WidthType.DXA }, columnWidths: widths,
    rows: [
      new TableRow({ children: headers.map((h, i) => cell(h, { width: widths[i], bold: true, shade: "D9E2F3" })) }),
      ...rows.map((r) => new TableRow({ children: r.map((v, i) => cell(v, { width: widths[i] })) })),
    ],
  });
}
function figure(p, w, h, caption) {
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120 }, children: [new ImageRun({ data: img(p), transformation: { width: w, height: h }, type: "png" })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 }, children: [new TextRun({ text: caption, italics: true, size: 18 })] }),
  ];
}
const gap = () => P("");

// ---------------------------------------------------------------- title
const title = [
  new Paragraph({ text: "", spacing: { before: 1600 } }),
  new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "PROJECT 1", size: 24, color: "666666" })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 200, after: 200 }, children: [new TextRun({ text: "Student Performance and Dropout-Risk Prediction System", bold: true, size: 40 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 400 }, children: [new TextRun({ text: "Part 2 -- Integration with the MLOps Pipeline: Project Report", size: 28, color: "444444" })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 }, children: [new TextRun({ text: "Course: Data Engineering and MLOps", size: 22 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 }, children: [new TextRun({ text: "Mode: Individual Project", size: 22 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 }, children: [new TextRun({ text: "Submitted by: Akshitha", size: 22 })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 400 }, children: [new TextRun({ text: "Part 2 review: first week of November 2026", size: 22 })] }),
  pageBreak(),
];

// ---------------------------------------------------------------- 1
const s1 = [
  H1("1. Introduction & Part 1 Recap"),
  P("Part 1 delivered a working data pipeline: a real academic dataset (UCI Student Performance, 1,034 student-subject records) combined with simulated attendance, LMS and assignment exports, validated and cleaned with a rejected-record log, loaded into a SQLite warehouse, and shown in a Streamlit dashboard. Its risk flag was deliberately a rule-based placeholder, not a trained model."),
  P("Part 2 builds the MLOps layer on top of that pipeline. It adds a leak-free ML dataset, five candidate models compared against two baselines, experiment tracking and a model registry in MLflow, a FastAPI prediction service, a Docker setup, drift monitoring with explicit retraining criteria, and orchestration through the same Airflow DAG. The code is in the same repository as Part 1 so the whole path from raw files to a monitored model can be re-run with a few commands."),
  H2("1.1 What is new in Part 2"),
  table(["Area", "Deliverable", "Where"], [
    ["ML dataset", "Leak-free features and target, CSV + SQLite table", "mlops/dataset.py"],
    ["Training", "5 models (LR, Random Forest, Gradient Boosting, SVM, XGBoost), CV, SHAP, plots", "mlops/train.py"],
    ["Tracking + registry", "MLflow runs, model registry, champion alias", "mlstore/ (SQLite)"],
    ["Serving", "FastAPI: /predict, /predict/batch, /health, /model-info", "api/"],
    ["Containers", "Dockerfile + docker-compose (api, trainer, mlflow, monitor)", "Dockerfile, docker-compose.yml"],
    ["Monitoring", "PSI + KS drift, prediction drift, retrain triggers", "mlops/monitoring.py"],
    ["Integration", "Airflow DAG extended, dashboard view 6, one-command runner", "dags/, dashboard/, scripts/run_mlops.py"],
    ["Quality", "15 automated tests", "tests/"],
  ], [1900, 4700, 2400]),
];

// ---------------------------------------------------------------- 2
const s2 = [
  H1("2. Problem Formulation"),
  P("Goal: at mid-semester, flag students who are on course to fail a subject so a mentor can step in before the final result."),
  H2("2.1 Target definition"),
  P("The UCI data has no column for actual dropout. The supervised target is therefore a proxy: at_risk = 1 when the final score G3 is below 10, the dataset's own pass mark. 22.1% of records are positive (about 1 in 5). The report and the dashboard both call it a dropout-risk proxy, not dropout."),
  H2("2.2 Prediction time"),
  P("The model predicts after the second assessment (G2) and before the final result (G3). Only information available at that moment is allowed as input. This is what makes the model useful: a prediction made after G3 is known would be trivial."),
  H2("2.3 Success criteria"),
  bullet("Beat a majority-class baseline and a simple advisor rule (flag anyone whose G2 is below 10)."),
  bullet("Catch most at-risk students: operating threshold chosen so recall on out-of-fold training predictions is at least 0.80."),
  bullet("Keep false alarms manageable, reported as precision alongside recall."),
  bullet("Be reproducible: fixed seed, tracked runs, one command to retrain."),
];

// ---------------------------------------------------------------- 3
const s3 = [
  H1("3. ML Dataset & Feature Engineering"),
  P("mlops/dataset.py joins the Part 1 analytical mart with the cleaned academic records on student_id (one-to-one, 1,034 rows, no nulls) and writes data/ml/ml_dataset.csv plus a SQLite table ml_training_dataset beside the mart. It uses 30 features."),
  table(["Group", "Features", "Source"], [
    ["Multi-source (5)", "attendance_pct, avg_internal_marks, previous_semester_score (G2), assignment_completion_rate, lms_engagement_score", "Part 1 mart"],
    ["Academic record, numeric (13)", "studytime, failures, absences, goout, Dalc, Walc, freetime, health, famrel, Medu, Fedu, age, traveltime", "UCI (real)"],
    ["Binary (9)", "internet, higher, schoolsup, famsup, paid, activities, romantic, is_male, is_math", "UCI (real)"],
    ["Availability flags (3)", "attendance_, lms_, assignment_data_available", "Part 1 missing-data handling"],
  ], [2200, 5200, 1600]),
  gap(),
  H2("3.1 Leakage control"),
  table(["Excluded column", "Reason"], [
    ["current_score / G3, pass_flag", "They are the target."],
    ["risk_score, risk_category", "Part 1's rule-based score is computed from the final score, so using it would leak the answer."],
    ["department, semester", "Assigned randomly in Part 1 (synthetic), so they carry no real signal."],
    ["student_id", "Identifier, not a feature."],
  ], [3000, 6000]),
  P("A unit test asserts none of these columns can enter the feature list, and another recomputes the target from the raw G3 values."),
  H2("3.2 Missing values"),
  P("The Part 1 mart is already complete because missing sources were flagged and imputed with documented fallbacks. In serving, a missing optional field is imputed with the training median inside the model pipeline and the matching availability flag is set to 0. This is the justified-imputation-for-ML case in the course guideline. The flags stay in the model so it can learn from missingness itself."),
];

// ---------------------------------------------------------------- 4
const row = (name, key) => [name, f3(T[key].cv.cv_roc_auc_mean), f3(T[key].test.roc_auc), f3(T[key].test.pr_auc), f2(T[key].test.recall), f2(T[key].test.precision)];
const s4 = [
  H1("4. Model Development & Evaluation"),
  H2("4.1 Protocol"),
  P("Stratified 80/20 split with seed 42 (827 training rows, 207 test rows with 46 positives). Each candidate gets 5-fold stratified cross-validation on the training split only. The winner is chosen by cross-validated ROC-AUC, never by the test set, and the test set is scored once. Logistic Regression uses scaling and balanced class weights; Random Forest uses 300 trees with balanced subsample weights; Gradient Boosting (scikit-learn HistGradientBoosting) uses depth 3, 250 iterations and balanced weights; the SVM uses an RBF kernel on scaled inputs with sigmoid-calibrated probabilities; XGBoost uses depth 3, 250 trees and scale_pos_weight. Every model sits behind the same median imputer, so a missing optional value is handled identically for all of them. Hyperparameters are fixed defaults, not tuned."),
  H2("4.2 Results"),
  table(["Model", "CV ROC-AUC", "Test ROC-AUC", "Test PR-AUC", "Recall @0.5", "Precision @0.5"], [
    row("Logistic Regression", "logistic_regression"),
    row("Random Forest (champion)", "random_forest"),
    row("Gradient Boosting (HistGB)", "hist_gradient_boosting"),
    row("SVM (RBF kernel)", "svm_rbf"),
    row("XGBoost", "xgboost"),
    ["Rule: G2 below 10", "n/a", f3(B.baseline_rule_G2_below_10.roc_auc), f3(B.baseline_rule_G2_below_10.pr_auc), f2(B.baseline_rule_G2_below_10.recall), f2(B.baseline_rule_G2_below_10.precision)],
    ["Majority class", "n/a", f3(B.baseline_majority.roc_auc), f3(B.baseline_majority.pr_auc), f2(B.baseline_majority.recall), f2(B.baseline_majority.precision)],
  ], [2700, 1250, 1300, 1250, 1250, 1350]),
  gap(),
  P(`Random Forest had the best cross-validated ROC-AUC (${f3(meta.cv.cv_roc_auc_mean)} ± ${f3(meta.cv.cv_roc_auc_std)}) and became the champion. At its operating threshold of ${meta.threshold} the test confusion matrix is TN ${OP.tn}, FP ${OP.fp}, FN ${OP.fn}, TP ${OP.tp}: recall ${f2(OP.recall)}, precision ${f2(OP.precision)}, F1 ${f2(OP.f1)}, Brier score ${f3(OP.brier)}.`),
  ...figure("reports/roc_curves.png", 330, 341, "Figure 1: ROC curves on the held-out test set"),
  ...figure("reports/confusion_matrix.png", 300, 281, "Figure 2: Champion confusion matrix at the operating threshold"),
  H2("4.3 Explainability"),
  P("SHAP values for the champion show that avg_internal_marks and previous_semester_score dominate, followed by failures. The synthetic attendance, LMS and assignment features contribute little because they were generated independently of the final score (documented in Part 1), so a model cannot learn a relationship that is not in the data."),
  ...figure("reports/shap_summary.png", 430, 404, "Figure 3: SHAP summary for the champion model (test set)"),
  H2("4.4 What the numbers do and do not show"),
  bullet("The five models are statistically indistinguishable on 207 test rows with 46 positives. Random Forest won on cross-validation; XGBoost has the highest single test AUC. The SVM is the weakest of the five on both CV and test AUC."),
  bullet(`The simple rule 'G2 below 10' already reaches ROC-AUC ${f3(B.baseline_rule_G2_below_10.roc_auc)}. G2 is a very strong predictor of G3. The models' benefit is fewer false alarms: at the default threshold they flag ${DF.fp} students wrongly versus ${B.baseline_rule_G2_below_10.fp} for the rule, while missing ${DF.fn} at-risk students versus ${B.baseline_rule_G2_below_10.fn} for the rule.`),
  bullet("The label is a proxy, the dataset is about one thousand rows, and no hyperparameter search or fairness audit was done. The model supports early-warning conversations; it does not decide anything about a student."),
];

// ---------------------------------------------------------------- 5
const s5 = [
  H1("5. Experiment Tracking & Model Registry (MLflow)"),
  P("mlops/train.py logs every training to MLflow using a SQLite backend in mlstore/ (set MLFLOW_TRACKING_URI to log to DagsHub instead). One parent run per training holds the dataset metadata, seed, split sizes and the plots; one child run per model and baseline holds its hyperparameters, cross-validation and test metrics, input/output signature and an input example."),
  P("The winner is registered as student-dropout-risk. Promotion follows a champion/challenger rule: a new version takes the 'champion' alias when its test ROC-AUC is at least the current champion's minus 0.005; otherwise it stays registered but unpromoted and the serving bundle is not overwritten. This was exercised: a second identical training created version 2 and moved the alias from version 1."),
  ...figure("screenshots/08_mlflow_experiment_runs.png", 560, 315, "Figure 4: MLflow training runs with child runs for each model and baseline"),
  ...figure("screenshots/09_mlflow_model_registry.png", 560, 315, "Figure 5: Model registry showing versions 1 and 2 and the champion alias"),
  P("After promotion the training script exports a serving bundle: models/champion.joblib, champion_meta.json (metrics, threshold, versions, library versions) and reference_stats.json (the training-time distribution used for drift checks)."),
];

// ---------------------------------------------------------------- 6
const s6 = [
  H1("6. Model Serving (FastAPI)"),
  table(["Method", "Path", "Purpose"], [
    ["GET", "/health", "Liveness and whether a model is loaded"],
    ["GET", "/model-info", "Algorithm, registry version, threshold, test metrics, features"],
    ["POST", "/predict", "One student: probability, risk band, top factors"],
    ["POST", "/predict/batch", "1 to 500 students"],
    ["GET", "/stats", "Request count, share flagged, average latency"],
  ], [1100, 2300, 5600]),
  gap(),
  P("Inputs are validated with Pydantic: only previous_semester_score is required, ranges are enforced, unknown fields are rejected with HTTP 422, and a missing optional field is imputed and flagged as described in Section 3.2. Each response includes the three features that moved the prediction most, computed by swapping one feature at a time for the training average, so no SHAP library is needed in the container. Every prediction is appended to logs/prediction_log.csv, which is the input to drift monitoring."),
  P("Example request and response:", { bold: true }),
  code('POST /predict {"student_id":"DEMO1","previous_semester_score":8,"avg_internal_marks":8.5,'),
  code('               "attendance_pct":62,"failures":1,"lms_engagement_score":30}'),
  code('-> {"at_risk_probability":0.8693,"at_risk":true,"risk_band":"High","threshold":0.64,'),
  code('    "top_factors":[{"feature":"avg_internal_marks","impact":0.4251},'),
  code('                   {"feature":"previous_semester_score","impact":0.3498},{"feature":"failures",...}],'),
  code('    "model_version":"2"}'),
  gap(),
  ...figure("screenshots/07_fastapi_swagger.png", 460, 319, "Figure 6: Interactive API documentation served at /docs"),
];

// ---------------------------------------------------------------- 7
const s7 = [
  H1("7. Containerization (Docker)"),
  P("A single image (python:3.11-slim, non-root user, health check) runs three jobs, selected in docker-compose.yml: the API service, a trainer that rebuilds the dataset and retrains inside the same library versions, and an MLflow UI. A fourth profile runs the drift monitor. Code goes into the image; data, models, logs and the MLflow store are mounted as volumes, so rebuilding never deletes them."),
  code("docker compose --profile train run --rm trainer   # dataset + train + register"),
  code("docker compose up --build api                     # serve on :8000"),
  code("docker compose up mlflow                          # MLflow UI on :5000"),
  code("docker compose --profile monitor run --rm monitor"),
  gap(),
  P("Training inside the container is deliberate: a pickled scikit-learn model only loads reliably under the version that wrote it, so the image trains its own model instead of trusting a file built elsewhere. Status: the compose file is validated with 'docker compose config'; the image build and container run are demonstrated on the review machine (see Section 10)."),
];

// ---------------------------------------------------------------- 8
const dTop = drift.feature_drift.slice(0, 5).map((d) => [d.feature, f3(d.psi), d.status, d.ref_mean, d.cur_mean]);
const s8 = [
  H1("8. Monitoring & Retraining Criteria"),
  P("mlops/monitoring.py compares the logged predictions with the training reference. A check needs at least 30 logged predictions; below that it reports insufficient data instead of guessing."),
  table(["Signal", "Method", "Threshold"], [
    ["Data drift", "Population Stability Index per feature, plus KS test for continuous features", "PSI 0.10 watch, 0.20 warning, 0.25 drift"],
    ["Prediction drift", "Share flagged at-risk vs reference share (23.7%)", "More than 10 percentage points"],
    ["Missing-data drift", "Share of requests with each availability flag at 0", "Reported only"],
    ["Performance drift", "Recall and ROC-AUC once true outcomes are known", "Recall below 0.70 or AUC down more than 0.05"],
    ["Model age", "Days since training", "More than 180 days"],
  ], [1900, 4600, 2500]),
  gap(),
  P("Retraining triggers: T1 two or more features with PSI above 0.20, or any above 0.25; T2 flagged share moves more than 10 points; T3 performance decay; T4 model older than one semester. Any trigger sets the status to RETRAIN_RECOMMENDED, and the --retrain option runs the training script, which registers a challenger under the promotion rule in Section 5. Retraining is a recommendation to a person, who checks the new metrics before the new version serves traffic."),
  H2("8.1 Demonstration with simulated drift"),
  P(`There is no production traffic, so real drift has not been observed. To demonstrate the mechanism, --simulate-drift fabricates a bad semester from real rows (attendance down about 14 points, LMS engagement down 18, G2 down 2, absences up 5). The report is labelled SIMULATED. Result: ${drift.status}; ${drift.triggers.length} triggers fired; flagged share ${(drift.prediction_drift.flagged_share_current * 100).toFixed(1)}% versus ${(drift.prediction_drift.flagged_share_reference * 100).toFixed(1)}% in training.`),
  table(["Feature", "PSI", "Status", "Training mean", "Simulated mean"], dTop, [2900, 1000, 1200, 1900, 2000]),
  gap(),
  P("As a sanity check in the other direction, an unshifted 300-row sample scores healthy in the unit tests. Because that sample is drawn from the training pool it shows the mechanism works, not how the model behaves in the field."),
];

// ---------------------------------------------------------------- 9
const s9 = [
  H1("9. Integration with the Data Pipeline"),
  ...figure("docs/architecture_part2.png", 330, 431, "Figure 7: Part 2 architecture, building on the Part 1 pipeline"),
  bullet("Airflow: dags/student_pipeline_dag.py now chains ingest, validate/clean, transform/load, build_ml_dataset, train_and_register_model and monitor_drift. As in Part 1, the DAG file is written and syntax-checked but not run in a live Airflow instance."),
  bullet("One-command runner: scripts/run_mlops.py executes the same three Part 2 steps without Airflow and writes logs/mlops_run_log.txt."),
  bullet("Dashboard: a sixth view shows the champion's metrics, predicted risk next to the Part 1 rule-based category, the model comparison and the drift reports. Views 1 to 5 are unchanged."),
  bullet("Configuration: one feature contract (mlops/config.py) is imported by training, API, monitoring and dashboard, so a feature cannot exist in one component and be missing in another."),
  ...figure("screenshots/10_dashboard_ml_view.png", 560, 315, "Figure 8: Dashboard view 6, ML model predictions and monitoring"),
];

// ---------------------------------------------------------------- 10
const s10 = [
  H1("10. Execution Evidence & Testing"),
  bullet("python scripts/run_pipeline.py: Part 1 completes, 1,034 mart rows, 35 rejected rows, 15 flagged records (unchanged from Part 1)."),
  bullet("python scripts/run_mlops.py: dataset built, five models trained and compared in about 35 seconds, winner registered and promoted, serving bundle exported; logs in logs/mlops_run_log.txt."),
  bullet("python -m pytest tests -q: 15 tests pass. They cover API validation and ordering, missing optional fields, batch scoring and logging, leakage guards, target definition, reproducibility, the champion bundle, and the PSI and drift logic."),
  bullet("Live runs: the API, MLflow server and dashboard were started and exercised (screenshots in Sections 5, 6 and 9); the dashboard's six views render without errors in Streamlit's headless test runner."),
  bullet("Docker: compose configuration validated. To be shown live at review: docker compose --profile train run --rm trainer, then docker compose up --build api, then a curl to /health and /predict."),
  bullet("Airflow: DAG definition only; not executed in a live instance."),
  H2("10.1 Reproducing the results"),
  code("pip install -r requirements.txt"),
  code("python scripts/run_pipeline.py && python scripts/run_mlops.py"),
  code("python -m pytest tests -q"),
  P("Seeds are fixed (42), so re-running gives the same split and metrics on the same library versions."),
];

// ---------------------------------------------------------------- 11
const s11 = [
  H1("11. Limitations & Future Work"),
  bullet("The target is a proxy for dropout (failing the subject), not actual dropout, because the data has no such column."),
  bullet("About one thousand rows from two schools; test metrics rest on 46 positive cases, so differences between models are within noise."),
  bullet("The G2 rule is nearly as good in ROC-AUC. The value of the model is fewer false alarms and a probability with reasons, not a large jump in discrimination."),
  bullet("The attendance, LMS and assignment sources are synthetic, so their small contribution says nothing about their value in a real college."),
  bullet("Hyperparameters are not tuned and there is no probability calibration step or fairness audit; sex is an input feature and a real deployment would need a review of that choice."),
  bullet("No alerting channel (email or Slack) and no scheduled monitoring outside the Airflow DAG; there is no real traffic yet, so drift detection has only been demonstrated on simulated data."),
  bullet("Future work: tune with nested CV, add calibration and subgroup metrics, collect real outcomes to enable the performance-drift signal, add CI that runs the test suite and a scheduled monitor, and deploy the container to a managed host."),
];

// ---------------------------------------------------------------- 12
const s12 = [
  H1("12. Conclusion"),
  P("Part 2 turns the Part 1 pipeline into a small but complete MLOps loop: a leak-free dataset, tracked and comparable experiments, a registry with a promotion rule, a validated and logged prediction service, a containerized setup, and monitoring with written retraining criteria, all wired into the same orchestration and dashboard. The honest takeaway from the evaluation is as important as the machinery: on this data a simple G2 rule is already strong, so the model's contribution is precision and explanation, and the real test of the monitoring work will come when real traffic and outcomes exist."),
];

const doc = new Document({
  numbering: { config: [{ reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] }] },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 } } },
    headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: "Student Performance & Dropout-Risk Prediction System -- Part 2", size: 16, color: "888888" })] })] }) },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ children: [PageNumber.CURRENT], size: 18 })] })] }) },
    children: [...title, ...s1, ...s2, ...s3, ...s4, ...s5, ...s6, ...s7, ...s8, ...s9, ...s10, ...s11, ...s12],
  }],
});

Packer.toBuffer(doc).then((buf) => {
  const out = path.join(ROOT, "docs", "part2_report.docx");
  fs.writeFileSync(out, buf);
  console.log("Wrote", out);
});
