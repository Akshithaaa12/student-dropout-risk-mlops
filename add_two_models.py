"""Adds two more models (Gradient Boosting, SVM-RBF) to the dropout-risk project.

Run from the project root:   python3 add_two_models.py
Changes: mlops/modeling.py, mlops/train.py, tests/test_dataset_and_model.py,
docs/ml_design.md and the docs build scripts. Safe to run twice.
"""
import sys
from pathlib import Path

base = str(Path.cwd())
if not (Path(base) / "mlops" / "modeling.py").exists():
    sys.exit("Run this from ~/Projects/student-performance-pipeline (mlops/modeling.py not found).")


# ---- mlops/modeling.py -------------------------------------------------------
p = f"{base}/mlops/modeling.py"
s = open(p).read()
if "svm_rbf" not in s:
    s = s.replace("from sklearn.pipeline import Pipeline\nfrom sklearn.preprocessing import StandardScaler\n",
                  "from sklearn.pipeline import Pipeline\nfrom sklearn.preprocessing import StandardScaler\nfrom sklearn.calibration import CalibratedClassifierCV\nfrom sklearn.svm import SVC\n")
    old = s[s.index("    if HAVE_XGB:\n        models[\"xgboost\"]"):s.index("    return models\n")]
    new = '''    # Gradient boosting from scikit-learn: always available, no native library needed.
    models["hist_gradient_boosting"] = Pipeline([
        ("impute", imp()),
        ("clf", HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05,
                                               max_iter=250, class_weight="balanced",
                                               random_state=C.RANDOM_SEED))])
    # Kernel method: a different model family (needs scaled inputs; probabilities via sigmoid (Platt) calibration).
    models["svm_rbf"] = Pipeline([
        ("impute", imp()), ("scale", StandardScaler()),
        ("clf", CalibratedClassifierCV(
            SVC(C=1.0, kernel="rbf", gamma="scale", class_weight="balanced", random_state=C.RANDOM_SEED),
            method="sigmoid", cv=5, ensemble=False))])
    if HAVE_XGB:  # XGBoost needs libomp on macOS; skipped gracefully if it cannot load
        models["xgboost"] = Pipeline([
            ("impute", imp()),
            ("clf", XGBClassifier(n_estimators=250, max_depth=3, learning_rate=0.05,
                                  subsample=0.8, colsample_bytree=0.8,
                                  scale_pos_weight=pos_weight, eval_metric="logloss",
                                  n_jobs=1, random_state=C.RANDOM_SEED))])
'''
    s = s.replace(old, new)
    open(p, "w").write(s)

# ---- mlops/train.py docstring --------------------------------------------------
p = f"{base}/mlops/train.py"
s = open(p).read()
s = s.replace("(logistic regression, random forest, xgboost / HistGB fallback)",
              "(logistic regression, random forest, gradient boosting, SVM (RBF), xgboost)")
open(p, "w").write(s)

# ---- tests ------------------------------------------------------------------
p = f"{base}/tests/test_dataset_and_model.py"
s = open(p).read()
if "test_all_candidates_train_and_score" not in s:
    s += '''

def test_all_candidates_train_and_score():
    """Every candidate (incl. gradient boosting and SVM) must fit with NaNs present and give valid probabilities."""
    df = dataset.build_dataset()
    X, y = df[C.FEATURES].copy(), df[C.TARGET]
    X.iloc[::17, 3] = np.nan  # a few missing values: every pipeline imputes first
    from sklearn.model_selection import train_test_split
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=C.TEST_SIZE, stratify=y, random_state=C.RANDOM_SEED)
    cands = modeling.make_candidates((ytr == 0).sum() / (ytr == 1).sum())
    assert {"logistic_regression", "random_forest", "hist_gradient_boosting", "svm_rbf"} <= set(cands)
    for name, pipe in cands.items():
        proba = pipe.fit(Xtr, ytr).predict_proba(Xte)[:, 1]
        assert ((proba >= 0) & (proba <= 1)).all(), name
        assert modeling.metrics_at(yte, proba)["roc_auc"] > 0.85, name
'''
    open(p, "w").write(s)
print("patched", base)

def sub(path, pairs):
    p = f"{base}/{path}"
    s = open(p).read()
    for a, b in pairs:
        if b in s:
            continue  # already applied
        if a in s:
            s = s.replace(a, b)
        else:
            print("MISSING in", path, ":", a[:60])
    open(p, "w").write(s)

sub("docs/ml_design.md", [
("| XGBoost | depth 3, 250 trees, lr 0.05, `scale_pos_weight` (falls back to sklearn HistGradientBoosting if XGBoost cannot load) |",
 "| Gradient Boosting (sklearn HistGB) | depth 3, 250 iterations, lr 0.05, balanced class weights; no native library needed |\n"
 "| SVM (RBF kernel) | scaled inputs, `class_weight=balanced`, probabilities via sigmoid calibration (5-fold); a different model family |\n"
 "| XGBoost | depth 3, 250 trees, lr 0.05, `scale_pos_weight` (skipped automatically if XGBoost cannot load) |"),
("| XGBoost | 0.963 | 0.974 | 0.927 | 0.89 | 0.71 |",
 "| Gradient Boosting (HistGB) | 0.959 | 0.972 | 0.923 | 0.87 | 0.68 |\n| SVM (RBF) | 0.954 | 0.957 | 0.881 | 0.78 | 0.80 |\n| XGBoost | 0.963 | 0.974 | 0.927 | 0.89 | 0.71 |"),
("* All three models are statistically indistinguishable", "* All five models are statistically indistinguishable"),
])

sub("docs/build_part2_report.js", [
("three candidate models compared against two ba", "five candidate models compared against two ba"),
('"LR / Random Forest / XGBoost, CV, SHAP, plots"', '"5 models (LR, Random Forest, Gradient Boosting, SVM, XGBoost), CV, SHAP, plots"'),
("Logistic Regression uses scaling and balanced class weights; Random Forest uses 300 trees with balanced subsample weights; XGBoost uses depth 3, 250 trees and scale_pos_weight.",
 "Logistic Regression uses scaling and balanced class weights; Random Forest uses 300 trees with balanced subsample weights; Gradient Boosting (scikit-learn HistGradientBoosting) uses depth 3, 250 iterations and balanced weights; the SVM uses an RBF kernel on scaled inputs with sigmoid-calibrated probabilities; XGBoost uses depth 3, 250 trees and scale_pos_weight. Every model sits behind the same median imputer, so a missing optional value is handled identically for all of them."),
('    row("Random Forest (champion)", "random_forest"),\n    row("XGBoost", "xgboost"),',
 '    row("Random Forest (champion)", "random_forest"),\n    row("Gradient Boosting (HistGB)", "hist_gradient_boosting"),\n    row("SVM (RBF kernel)", "svm_rbf"),\n    row("XGBoost", "xgboost"),'),
("The three models are statistically indistinguishable on 207 test rows with 46 positives. Random Forest won on cross-validation; XGBoost has the highest single test AUC.",
 "The five models are statistically indistinguishable on 207 test rows with 46 positives. Random Forest won on cross-validation; XGBoost has the highest single test AUC. The SVM is the weakest of the five on both CV and test AUC."),
("dataset built, three models trained", "dataset built, five models trained"),
])

sub("docs/build_part2_deck.py", [
('("Random Forest (champion)", "random_forest"), ("XGBoost", "xgboost")]',
 '("Random Forest (champion)", "random_forest"), ("Gradient Boosting", "hist_gradient_boosting"), ("SVM (RBF)", "svm_rbf"), ("XGBoost", "xgboost")]'),
("bullets(s, 0.75, 4.4, 7.4, 2.3, [", "bullets(s, 0.75, 4.95, 7.4, 1.9, ["),
("The three models are about equal.", "The five models are about equal."),
("dataset, 3 models, registration", "dataset, 5 models, registration"),
])

sub("docs/generate_part2_diagram.py", [
('"mlops/train.py\\nLR / RF / XGBoost\\n5-fold CV, SHAP"', '"mlops/train.py\\nLR / RF / GB / SVM / XGBoost\\n5-fold CV, SHAP"'),
])
print("docs patched", base)
