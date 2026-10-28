"""Build the Part 2 review deck from the Part 1 CMRIT deck (keeps its look, logo, footer).
Run from the project root:  python docs/build_part2_deck.py
All numbers come from models/champion_meta.json and reports/*.json."""
import copy, json
from pathlib import Path
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from lxml import etree
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "Student_Performance_Dropout_Risk_Presentation.pptx"
OUT = ROOT / "docs" / "Student_Performance_Dropout_Risk_Part2_Presentation.pptx"
meta = json.loads((ROOT / "models/champion_meta.json").read_text())
drift = json.loads((ROOT / "reports/drift_report_simulated.json").read_text())
T, B, OP, DF = meta["all_models"], meta["baselines"], meta["metrics_test_operating_threshold"], meta["metrics_test_default_threshold"]
NAVY, INK, GREY, RED = RGBColor(0x16, 0x28, 0x3F), RGBColor(0x23, 0x32, 0x4A), RGBColor(0x6C, 0x6D, 0x6F), RGBColor(0xC9, 0x34, 0x2A)

prs = Presentation(str(SRC))
slides = list(prs.slides)
S_TITLE, S_ARCH1, S_CONTENT, S_THANKS = slides[0], slides[3], slides[10], slides[15]
layout = S_CONTENT.slide_layout

# ---------------------------------------------------------------- helpers
def set_text(shape, text):
    """Replace text keeping the first run's formatting."""
    p = shape.text_frame.paragraphs[0]
    r0 = p.runs[0]
    r0.text = text
    for r in p.runs[1:]:
        r._r.getparent().remove(r._r)

def new_slide(title, page):
    s = prs.slides.add_slide(layout)
    for sh in list(s.shapes):  # drop any placeholders from layout
        sh._element.getparent().remove(sh._element)
    for sh in list(S_CONTENT.shapes)[:9]:  # chrome: bar, header, title, rule, card, footer
        s.shapes._spTree.append(copy.deepcopy(sh._element))
    sh = list(s.shapes)
    set_text(sh[3], title)
    # page number run (second run holds the number)
    runs = sh[8].text_frame.paragraphs[0].runs
    runs[-1].text = f"   {page}"
    return s

def style_run(r, size, bold=False, italic=False, color=INK, font="Calibri"):
    r.font.size, r.font.bold, r.font.italic, r.font.name = Pt(size), bold, italic, font
    r.font.color.rgb = color

def textbox(s, x, y, w, h, paras, size=15, anchor=MSO_ANCHOR.TOP):
    """paras: list of str | (str, dict(bold,italic,color,size,bullet,mono))"""
    tb = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    first = True
    for item in paras:
        text, o = (item, {}) if isinstance(item, str) else item
        p = tf.paragraphs[0] if first else tf.add_paragraph()
        first = False
        r = p.add_run(); r.text = text
        style_run(r, o.get("size", size), o.get("bold", False), o.get("italic", False),
                  o.get("color", INK), "Consolas" if o.get("mono") else "Calibri")
        pPr = p._p.get_or_add_pPr()
        if o.get("bullet", True) and not o.get("mono") and not o.get("bold") and not o.get("italic"):
            pPr.set("marL", "228600"); pPr.set("indent", "-228600")
            sa = etree.SubElement(pPr, "{http://schemas.openxmlformats.org/drawingml/2006/main}spcAft")
            etree.SubElement(sa, "{http://schemas.openxmlformats.org/drawingml/2006/main}spcPts").set("val", str(o.get("after", 900)))
            etree.SubElement(pPr, "{http://schemas.openxmlformats.org/drawingml/2006/main}buSzPct").set("val", "100000")
            etree.SubElement(pPr, "{http://schemas.openxmlformats.org/drawingml/2006/main}buChar").set("char", "●")
        else:
            p.space_after = Pt(o.get("after_pt", 5))
    return tb

def bullets(s, x, y, w, h, items, size=15):
    return textbox(s, x, y, w, h, items, size)

def head(s, x, y, w, text):
    return textbox(s, x, y, w, 0.3, [(text, {"bold": True, "size": 14, "bullet": False})])

def picture(s, path, x, y, w, h, caption=None):
    im = Image.open(ROOT / path); ar = im.width / im.height
    pw, ph = (w, w / ar) if w / h < ar else (h * ar, h)
    px, py = x + (w - pw) / 2, y
    pic = s.shapes.add_picture(str(ROOT / path), Inches(px), Inches(py), Inches(pw), Inches(ph))
    pic.line.color.rgb = RGBColor(0xD9, 0xDC, 0xE1); pic.line.width = Pt(0.75)
    if caption:
        textbox(s, x, py + ph + 0.05, w, 0.3, [(caption, {"italic": True, "size": 11, "color": GREY, "bullet": False})])
    return pic

def table(s, x, y, w, rows, col_w, size=12, row_h=0.32, bold_rows=()):
    n, m = len(rows), len(rows[0])
    gt = s.shapes.add_table(n, m, Inches(x), Inches(y), Inches(w), Inches(row_h * n))
    tbl = gt.table
    # strip the default style banding
    tblPr = tbl._tbl.tblPr; tblPr.set("firstRow", "0"); tblPr.set("bandRow", "0")
    for j, cw in enumerate(col_w): tbl.columns[j].width = Inches(cw)
    for i, r in enumerate(rows):
        tbl.rows[i].height = Inches(row_h)
        for j, v in enumerate(r):
            c = tbl.cell(i, j); c.text = ""
            c.margin_left = c.margin_right = Inches(0.08); c.margin_top = c.margin_bottom = Inches(0.03)
            c.vertical_anchor = MSO_ANCHOR.MIDDLE
            run = c.text_frame.paragraphs[0].add_run(); run.text = str(v)
            hdr = i == 0
            style_run(run, size, bold=hdr or i in bold_rows, color=RGBColor(255, 255, 255) if hdr else INK)
            c.fill.solid()
            c.fill.fore_color.rgb = NAVY if hdr else (RGBColor(0xF4, 0xF6, 0xF9) if i % 2 == 0 else RGBColor(255, 255, 255))
    return tbl

f2, f3 = (lambda v: f"{v:.2f}"), (lambda v: f"{v:.3f}")

# ---------------------------------------------------------------- build new slides
new = []
pg = 3  # slide 1 = title, slide 2 = Part 1 recap

# 3 Problem
s = new_slide("2. Problem & Prediction Target", pg); pg += 1
head(s, 0.75, 1.65, 11.8, "What we predict")
bullets(s, 0.75, 2.0, 11.8, 1.8, [
    "Which students are on course to fail a subject, at mid-semester, early enough for a mentor to step in.",
    f"Target: at_risk = 1 if the final score G3 is below 10 (the dataset's own pass mark). About {meta['baselines'] and 22}% of students are positive.",
    "The data has no real 'dropped out' column, so this is a proxy for dropout risk. I say that on the slides and in the report.",
])
head(s, 0.75, 4.15, 11.8, "When the prediction is made")
bullets(s, 0.75, 4.5, 11.8, 1.9, [
    "After the second assessment (G2), before the final result (G3). Only things known at that point are allowed as inputs.",
    "Part 1's risk_score is built from the final score, so using it would leak the answer. It is not a feature.",
])

# 4 Architecture
s = new_slide("3. Part 2 Architecture", pg); pg += 1
picture(s, "docs/architecture_part2.png", 0.8, 1.55, 6.0, 5.2)
bullets(s, 7.1, 1.7, 5.5, 5.0, [
    "Part 1 pipeline feeds a leak-free ML dataset.",
    "Training logs every run to MLflow and registers the winner as 'champion'.",
    "A FastAPI service serves the champion and logs each prediction.",
    "The monitor compares those logs with the training data (PSI, KS) and says when to retrain.",
    "Everything hangs off the same Airflow DAG and dashboard as Part 1.",
], size=14)

# 5 Features
s = new_slide("4. Features & Leakage Control", pg); pg += 1
table(s, 0.75, 1.65, 11.8, [
    ["Group", "What's in it", "Count"],
    ["Multi-source (Part 1 mart)", "attendance, internal marks, G2 score, assignment completion, LMS engagement", "5"],
    ["Academic record (real UCI)", "study time, failures, absences, going out, alcohol, health, family, age, ...", "13"],
    ["Yes/No fields", "internet, wants higher ed, extra support, paid classes, romantic, is_male, is_math, ...", "9"],
    ["Availability flags (Part 1)", "was attendance / LMS / assignment data present?", "3"],
], [2.9, 7.9, 1.0], size=12, row_h=0.4)
head(s, 0.75, 3.85, 11.8, "Left out on purpose")
bullets(s, 0.75, 4.2, 11.8, 2.4, [
    "G3, current_score, pass_flag: they are the answer. risk_score / risk_category: computed from G3.",
    "department, semester: assigned randomly in Part 1, so they carry no real signal.",
    "A test checks none of these can slip into the feature list. Missing values at serving time get the training median plus the flag set to 0.",
], size=14)

# 6 Models
s = new_slide("5. Models & Evaluation", pg); pg += 1
rows = [["Model", "CV ROC-AUC", "Test ROC-AUC", "Test PR-AUC", "Recall", "Precision"]]
for name, key in [("Logistic Regression", "logistic_regression"), ("Random Forest (champion)", "random_forest"), ("Gradient Boosting", "hist_gradient_boosting"), ("SVM (RBF)", "svm_rbf"), ("XGBoost", "xgboost")]:
    rows.append([name, f3(T[key]["cv"]["cv_roc_auc_mean"]), f3(T[key]["test"]["roc_auc"]), f3(T[key]["test"]["pr_auc"]), f2(T[key]["test"]["recall"]), f2(T[key]["test"]["precision"])])
rb = B["baseline_rule_G2_below_10"]; mb = B["baseline_majority"]
rows.append(["Rule: G2 below 10", "-", f3(rb["roc_auc"]), f3(rb["pr_auc"]), f2(rb["recall"]), f2(rb["precision"])])
rows.append(["Majority class", "-", f3(mb["roc_auc"]), f3(mb["pr_auc"]), f2(mb["recall"]), f2(mb["precision"])])
table(s, 0.75, 1.65, 7.4, rows, [2.6, 1.0, 1.1, 1.0, 0.8, 0.9], size=11, row_h=0.36, bold_rows=(2,))
bullets(s, 0.75, 4.95, 7.4, 1.9, [
    "80/20 stratified split, 5-fold CV on the train part. Winner picked by CV only, test scored once.",
    f"At threshold {meta['threshold']}: caught {OP['tp']} of {OP['tp']+OP['fn']} at-risk students, {OP['fp']} false alarms (recall {f2(OP['recall'])}, precision {f2(OP['precision'])}).",
    "Recall/precision in the table use the default 0.5 threshold.",
], size=13)
picture(s, "reports/roc_curves.png", 8.5, 1.6, 4.0, 4.9, "ROC curves, held-out test set")

# 7 Honest findings
s = new_slide("6. What the Results Actually Say", pg); pg += 1
bullets(s, 0.75, 1.7, 6.6, 5.0, [
    f"The five models are about equal. 207 test rows, only 46 at-risk, so the differences are noise.",
    f"The simple rule 'G2 below 10' already gets ROC-AUC {f3(rb['roc_auc'])}. G2 is just a very strong predictor of G3.",
    f"What the models really add: fewer false alarms. At 0.5 they wrongly flag {DF['fp']} students vs {rb['fp']} for the rule, but miss {DF['fn']} at-risk ones vs {rb['fn']}.",
    "SHAP: marks and G2 dominate, then past failures. The synthetic attendance / LMS columns barely matter because I generated them independently of G3.",
    "So it's an early-warning aid, not a decision-maker.",
], size=14)
picture(s, "reports/shap_summary.png", 7.7, 1.6, 4.9, 4.9, "SHAP summary, champion model")

# 8 MLflow
s = new_slide("7. Experiment Tracking & Model Registry (MLflow)", pg); pg += 1
picture(s, "screenshots/08_mlflow_experiment_runs.png", 0.75, 1.6, 5.9, 3.3, "One parent run per training, a child run per model")
picture(s, "screenshots/09_mlflow_model_registry.png", 6.85, 1.6, 5.7, 3.2, "Registered model: versions + 'champion' alias")
bullets(s, 0.75, 5.35, 11.8, 1.4, [
    "Each run logs params, CV + test metrics, plots, model signature. Winner is registered as student-dropout-risk.",
    "A new version becomes champion only if its test AUC is within 0.005 of the current one. Ran it twice: v2 took over from v1.",
], size=13)

# 9 FastAPI
s = new_slide("8. Model Serving with FastAPI", pg); pg += 1
picture(s, "screenshots/07_fastapi_swagger.png", 0.75, 1.6, 5.6, 3.9, "Swagger docs at /docs")
textbox(s, 6.7, 1.65, 5.9, 0.3, [("POST /predict", {"bold": True, "size": 14, "bullet": False})])
textbox(s, 6.7, 2.0, 5.9, 1.2, [
    ('{"student_id":"DEMO1","previous_semester_score":8,', {"mono": True, "size": 10.5, "after_pt": 1}),
    (' "avg_internal_marks":8.5,"attendance_pct":62,"failures":1}', {"mono": True, "size": 10.5, "after_pt": 6}),
    ('-> {"at_risk_probability":0.8693,"at_risk":true,"risk_band":"High",', {"mono": True, "size": 10.5, "after_pt": 1}),
    ('    "top_factors":[avg_internal_marks, previous_semester_score, failures]}', {"mono": True, "size": 10.5}),
])
bullets(s, 6.7, 3.35, 5.9, 3.3, [
    "Only G2 is required; missing fields are imputed and flagged. Bad input gets a 422.",
    "Reasons per student come from swapping one feature at a time for the average, so no SHAP in the container.",
    "Endpoints: /health, /model-info, /predict, /predict/batch, /stats.",
    "Every prediction is appended to a log, which feeds the monitor.",
], size=13)

# 10 Docker + orchestration
s = new_slide("9. Docker & Orchestration", pg); pg += 1
head(s, 0.75, 1.65, 5.8, "Docker (one image, three jobs)")
textbox(s, 0.75, 2.0, 5.8, 1.3, [
    ("docker compose --profile train run --rm trainer", {"mono": True, "size": 11, "after_pt": 2}),
    ("docker compose up --build api", {"mono": True, "size": 11, "after_pt": 2}),
    ("docker compose up mlflow", {"mono": True, "size": 11, "after_pt": 2}),
    ("docker compose --profile monitor run --rm monitor", {"mono": True, "size": 11}),
])
bullets(s, 0.75, 3.3, 5.8, 3.4, [
    "Non-root user, health check, code in the image, data/models/logs as volumes.",
    "Trainer runs inside the same image so the pickled model matches the library versions.",
    "Compose file validated with 'docker compose config'. The build + run is for the live demo.",
], size=13)
head(s, 6.9, 1.65, 5.7, "Airflow DAG (now 6 tasks)")
table(s, 6.9, 2.05, 5.7, [
    ["#", "Task"],
    ["1", "ingest_source_to_raw"],
    ["2", "validate_and_clean_raw_to_cleaned"],
    ["3", "transform_and_load_to_analytical_db"],
    ["4", "build_ml_dataset   (new)"],
    ["5", "train_and_register_model   (new)"],
    ["6", "monitor_drift   (new)"],
], [0.5, 5.2], size=12, row_h=0.36)
bullets(s, 6.9, 4.8, 5.7, 1.9, [
    "DAG file is written and syntax-checked, not run in a live Airflow (same as Part 1).",
    "python scripts/run_mlops.py runs tasks 4 to 6 without Airflow.",
], size=13)

# 11 Monitoring
s = new_slide("10. Monitoring & Retraining Criteria", pg); pg += 1
table(s, 0.75, 1.65, 6.4, [
    ["Trigger", "Fires when"],
    ["T1 data drift", "2+ features PSI > 0.20, or any > 0.25"],
    ["T2 prediction drift", "share flagged moves > 10 points"],
    ["T3 performance", "recall < 0.70 or AUC drops > 0.05 (needs real outcomes)"],
    ["T4 age", "model older than 180 days (a semester)"],
], [1.9, 4.5], size=11, row_h=0.42)
bullets(s, 0.75, 3.95, 6.4, 2.7, [
    "Drift = PSI per feature (+ KS test). Needs 30+ logged predictions, otherwise it says 'not enough data'.",
    "A trigger means 'retrain recommended'. A person checks the new version in MLflow before it serves.",
    "No real traffic yet, so real drift has not been seen. The demo is simulated, and labelled that way.",
], size=13)
head(s, 7.5, 1.65, 5.1, "Simulated bad semester (demo)")
dr = [["Feature", "PSI", "Mean: train -> sim"]]
for d in drift["feature_drift"][:5]:
    dr.append([d["feature"], f"{d['psi']:.2f}", f"{d['ref_mean']:.1f} -> {d['cur_mean']:.1f}"])
table(s, 7.5, 2.0, 5.1, dr, [2.5, 0.8, 1.8], size=11, row_h=0.34)
textbox(s, 7.5, 4.2, 5.1, 2.2, [
    (f"Result: {drift['status']}", {"bold": True, "size": 14, "bullet": False, "color": RED}),
    (f"Flagged share {drift['prediction_drift']['flagged_share_current']*100:.0f}% vs {drift['prediction_drift']['flagged_share_reference']*100:.0f}% in training; both T1 and T2 fired.", {"size": 13, "bullet": False}),
])

# 12 Dashboard
s = new_slide("11. Dashboard: ML View", pg); pg += 1
picture(s, "screenshots/10_dashboard_ml_view.png", 0.75, 1.55, 7.4, 4.2)
bullets(s, 8.4, 1.7, 4.2, 5.0, [
    "New 6th view next to the Part 1 ones.",
    "Champion metrics, predicted risk next to the old rule-based category.",
    "Tabs for model comparison and drift reports.",
    "Scores in the table are in-sample, so use the test metrics above for honest accuracy.",
], size=13)

# 13 Testing
s = new_slide("12. Testing & Evidence", pg); pg += 1
bullets(s, 0.75, 1.7, 11.8, 5.0, [
    "pytest: 15 tests pass. API (validation, ordering, missing fields, batch + logging), dataset/leakage, target definition, reproducibility, PSI + drift logic.",
    "python scripts/run_mlops.py: dataset, 5 models, registration and export in about 35 seconds. Same numbers on every run (seed 42).",
    "API, MLflow server and dashboard were started and used live; all 6 dashboard views load without errors.",
    "Found and fixed along the way: MLflow rejected the default model format, and the drift report had invalid JSON (NaN). Both fixed and re-tested.",
    "Not run live: Airflow DAG, Docker build (compose config validated only).",
], size=17)

# 14 Limitations
s = new_slide("13. Limitations & Future Work", pg); pg += 1
head(s, 0.75, 1.65, 5.8, "Limitations")
bullets(s, 0.75, 2.0, 5.8, 4.6, [
    "Label is a proxy (fail the subject), not actual dropout.",
    "About 1,000 rows, 46 positives in test.",
    "A plain G2 rule is nearly as good on AUC.",
    "Attendance / LMS / assignments are synthetic.",
    "No tuning, calibration or fairness check yet (sex is a feature).",
], size=13)
head(s, 6.9, 1.65, 5.7, "Next")
bullets(s, 6.9, 2.0, 5.7, 4.6, [
    "Collect real outcomes so performance drift can be measured.",
    "Hyperparameter search with nested CV, calibration, subgroup metrics.",
    "CI to run the tests, scheduled monitor with alerts.",
    "Deploy the container somewhere managed.",
], size=13)

# 15 Conclusion
s = new_slide("14. Conclusion", pg); pg += 1
bullets(s, 0.75, 1.7, 11.8, 5.0, [
    "Part 1's pipeline now feeds a full MLOps loop: dataset, tracked experiments, registry, API, Docker, monitoring, retraining rules.",
    "Honest result: on this data a simple rule is already strong. The model adds fewer false alarms and a reason per student.",
    "The real test for the monitoring is real traffic and real outcomes, which don't exist yet.",
    "Everything runs from the same repo: pip install, run_pipeline, run_mlops, pytest.",
], size=18)

# ---------------------------------------------------------------- tweak kept slides
for sh in S_TITLE.shapes:
    if sh.has_text_frame and "Part 1" in sh.text_frame.text:
        set_text(sh, "Data Engineering and MLOps  |  Individual Project (Part 2: MLOps Integration)")
# Part 1 recap slide = architecture slide, retitled, with a tighter caption
sh = list(S_ARCH1.shapes)
set_text(sh[3], "1. Recap: Part 1 Data Pipeline")
sh[8].text_frame.paragraphs[0].runs[-1].text = "   2"
set_text(sh[10], "Done in Part 1: 5 sources, ingest, validate/clean, SQLite star schema, dashboard (1,034 records, 35 rejected, 15 flagged). Part 2 builds on that pipeline.")
# second bullet: Part 1 said 'a real Airflow DAG', but the DAG file was never run in a live Airflow
p2 = sh[10].text_frame.paragraphs
if len(p2) > 1:
    r = p2[1].runs[0]; r.text = "Orchestration: Airflow DAG file (written and checked, not run in a live Airflow)."
    for extra in p2[1].runs[1:]: extra._r.getparent().remove(extra._r)

# ---------------------------------------------------------------- reorder / delete
sldIdLst = prs.slides._sldIdLst
all_slides = list(prs.slides)
els = list(sldIdLst)               # same order as all_slides
el_of = {id(sl): el for sl, el in zip(all_slides, els)}
keep = [S_TITLE, S_ARCH1] + all_slides[16:] + [S_THANKS]
keep_set = {id(sl) for sl in keep}
for sl in all_slides:
    if id(sl) not in keep_set:
        prs.part.drop_rel(el_of[id(sl)].rId)
        sldIdLst.remove(el_of[id(sl)])
for el in list(sldIdLst): sldIdLst.remove(el)
for sl in keep: sldIdLst.append(el_of[id(sl)])

prs.save(str(OUT))
print("Wrote", OUT, "slides:", len(prs.slides))
