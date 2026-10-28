import json

import numpy as np
import pandas as pd

from mlops import config as C
from mlops import dataset, modeling


def test_no_leakage_columns_in_features():
    banned = {"G3", "current_score", "pass_flag", "risk_score", "risk_category", "department", "semester", "student_id"}
    assert not banned & set(C.FEATURES)
    assert len(C.FEATURES) == len(set(C.FEATURES))


def test_dataset_shape_and_target():
    df = dataset.build_dataset()
    assert df["student_id"].is_unique
    assert list(df.columns) == ["student_id"] + C.FEATURES + [C.TARGET]
    assert df.isna().sum().sum() == 0
    assert set(df[C.TARGET].unique()) == {0, 1}
    assert 0.15 < df[C.TARGET].mean() < 0.30  # ~22% in the seeded data


def test_target_matches_definition():
    df = dataset.build_dataset()
    acad = pd.read_csv(C.CLEAN_DIR / "academic_records.csv").set_index("student_id")
    expected = (acad.loc[df["student_id"], "G3"].to_numpy() < C.PASS_MARK).astype(int)
    assert (df[C.TARGET].to_numpy() == expected).all()


def test_model_beats_majority_baseline_and_is_reproducible():
    df = dataset.build_dataset()
    X, y = df[C.FEATURES], df[C.TARGET]
    from sklearn.model_selection import train_test_split
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=C.TEST_SIZE, stratify=y, random_state=C.RANDOM_SEED)
    pos_w = (ytr == 0).sum() / (ytr == 1).sum()
    m = modeling.make_candidates(pos_w)["logistic_regression"].fit(Xtr, ytr)
    auc = modeling.metrics_at(yte, m.predict_proba(Xte)[:, 1])["roc_auc"]
    assert auc > 0.85
    m2 = modeling.make_candidates(pos_w)["logistic_regression"].fit(Xtr, ytr)
    assert np.allclose(m.predict_proba(Xte), m2.predict_proba(Xte))


def test_champion_bundle_consistent():
    meta = json.loads(C.CHAMPION_META.read_text())
    assert meta["features"] == C.FEATURES
    assert meta["metrics_test_default_threshold"]["roc_auc"] > 0.85
    assert 0 < meta["threshold"] < 1


def test_pick_threshold_respects_recall():
    y = np.array([0] * 80 + [1] * 20)
    p = np.concatenate([np.linspace(0, 0.6, 80), np.linspace(0.4, 1, 20)])
    t = modeling.pick_threshold(y, p, 0.8)
    assert ((p >= t) & (y == 1)).sum() / 20 >= 0.8


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
