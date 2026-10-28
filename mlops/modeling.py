"""Model definitions + evaluation helpers shared by training and tests."""

import numpy as np
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, average_precision_score, brier_score_loss,
                             confusion_matrix, f1_score, precision_score, recall_score,
                             roc_auc_score)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.calibration import CalibratedClassifierCV
from sklearn.svm import SVC

from mlops import config as C

try:  # XGBoost needs libomp on macOS; fall back gracefully if it can't load
    from xgboost import XGBClassifier
    HAVE_XGB = True
except Exception:  # pragma: no cover - environment dependent
    HAVE_XGB = False


def make_candidates(pos_weight: float) -> dict:
    """Return {name: sklearn Pipeline}. Every pipeline starts with a median
    imputer, so the serving API can accept missing values safely (the same
    justified-imputation rule used in Part 1)."""
    imp = lambda: SimpleImputer(strategy="median")  # noqa: E731
    models = {
        "logistic_regression": Pipeline([
            ("impute", imp()), ("scale", StandardScaler()),
            ("clf", LogisticRegression(C=0.5, class_weight="balanced", max_iter=2000,
                                       random_state=C.RANDOM_SEED))]),
        "random_forest": Pipeline([
            ("impute", imp()),
            ("clf", RandomForestClassifier(n_estimators=300, min_samples_leaf=3,
                                           class_weight="balanced_subsample",
                                           n_jobs=-1, random_state=C.RANDOM_SEED))]),
    }
    # Gradient boosting from scikit-learn: always available, no native library needed.
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
    return models


def make_baselines() -> dict:
    return {"baseline_majority": Pipeline([("impute", SimpleImputer(strategy="median")),
                                           ("clf", DummyClassifier(strategy="prior"))])}


def rule_baseline_scores(X) -> np.ndarray:
    """Naive advisor rule: flag anyone whose latest score (G2) is below the pass mark.
    Returned as a pseudo-probability so it can be scored like a model."""
    g2 = X["previous_semester_score"].to_numpy(dtype=float)
    return np.clip((C.PASS_MARK - g2 + 0.5) / 10.0 + 0.5, 0, 1)


def metrics_at(y_true, proba, threshold=0.5) -> dict:
    pred = (np.asarray(proba) >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, pred, labels=[0, 1]).ravel()
    return {
        "roc_auc": float(roc_auc_score(y_true, proba)),
        "pr_auc": float(average_precision_score(y_true, proba)),
        "accuracy": float(accuracy_score(y_true, pred)),
        "precision": float(precision_score(y_true, pred, zero_division=0)),
        "recall": float(recall_score(y_true, pred, zero_division=0)),
        "f1": float(f1_score(y_true, pred, zero_division=0)),
        "brier": float(brier_score_loss(y_true, proba)),
        "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
        "threshold": float(threshold),
    }


def pick_threshold(y_true, proba, min_recall=0.80) -> float:
    """Highest threshold that still catches >= min_recall of at-risk students
    (an advisor would rather over-flag than miss a student who needs help)."""
    y_true = np.asarray(y_true)
    best = 0.5
    for t in np.arange(0.05, 0.95, 0.01):
        pred = proba >= t
        rec = (pred & (y_true == 1)).sum() / max((y_true == 1).sum(), 1)
        if rec >= min_recall:
            best = float(round(t, 2))
    return best
