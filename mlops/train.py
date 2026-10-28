"""
Train, compare, track and register the dropout-risk models (Part 2, step 2).

    python -m mlops.train                 # normal run
    python -m mlops.train --no-register   # track only, skip the model registry

What it does
  1. loads data/ml/ml_dataset.csv, stratified 80/20 train/test split (seed 42)
  2. scores two baselines (majority class, "G2 below pass mark" rule)
  3. 5-fold stratified CV on the TRAIN split for each candidate model
     (logistic regression, random forest, gradient boosting, SVM (RBF), xgboost)
  4. selects the winner by CV ROC-AUC, evaluates it ONCE on the untouched test set
  5. logs params/metrics/plots/model to MLflow (one parent run, one child per model)
  6. registers the winner and applies champion/challenger promotion
  7. exports the serving bundle (models/champion.joblib + metadata + reference stats)
"""

import argparse
import json
import platform
import warnings
from datetime import datetime, timezone

import joblib
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import mlflow  # noqa: E402
import mlflow.sklearn  # noqa: E402
import sklearn  # noqa: E402
from mlflow.models import infer_signature  # noqa: E402
from mlflow.tracking import MlflowClient  # noqa: E402
from sklearn.base import clone  # noqa: E402
from sklearn.metrics import ConfusionMatrixDisplay, PrecisionRecallDisplay, RocCurveDisplay  # noqa: E402
from sklearn.model_selection import StratifiedKFold, cross_val_predict, cross_validate, train_test_split  # noqa: E402

from mlops import config as C  # noqa: E402
from mlops import modeling as M  # noqa: E402
from mlops import tracking  # noqa: E402

warnings.filterwarnings("ignore")
PROMOTION_TOLERANCE = 0.005  # challenger may be this much worse on test AUC and still be promoted


def load_xy():
    if not C.ML_DATASET_CSV.exists():
        raise SystemExit("Run `python -m mlops.dataset` first.")
    df = pd.read_csv(C.ML_DATASET_CSV)
    return df[C.FEATURES], df[C.TARGET].astype(int), df["student_id"]


def build_reference_stats(X_train: pd.DataFrame, y_train, test_metrics: dict) -> dict:
    """Training-time distribution snapshot used later by monitoring (PSI / KS)."""
    feats = {}
    for col in C.FEATURES:
        s = X_train[col].dropna().astype(float)
        uniq = np.unique(s)
        if len(uniq) <= 12:  # discrete / binary -> use category shares
            share = (s.value_counts(normalize=True)).sort_index()
            feats[col] = {"kind": "discrete", "values": [float(v) for v in share.index],
                          "share": [float(v) for v in share.values],
                          "mean": float(s.mean()), "std": float(s.std(ddof=0))}
        else:
            edges = np.unique(np.quantile(s, np.linspace(0, 1, 11)))
            counts, _ = np.histogram(s, bins=edges)
            feats[col] = {"kind": "continuous", "edges": [float(e) for e in edges],
                          "share": [float(c / counts.sum()) for c in counts],
                          "mean": float(s.mean()), "std": float(s.std(ddof=0)),
                          "sample": [float(v) for v in np.random.default_rng(C.RANDOM_SEED)
                                     .choice(s, size=min(400, len(s)), replace=False)]}
    return {"n_rows": int(len(X_train)), "positive_rate": float(np.mean(y_train)),
            "features": feats, "test_metrics_at_training": test_metrics}


def fig_to_file(fig, name):
    C.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = C.REPORT_DIR / name
    fig.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return path


def shap_summary(pipe, X_ref: pd.DataFrame):
    """Mean |SHAP| per feature for the winning model (None if SHAP can't run)."""
    try:
        import shap
        imp, est = pipe[:-1], pipe[-1]
        Xt = pd.DataFrame(imp.transform(X_ref), columns=C.FEATURES)
        if hasattr(est, "coef_"):
            expl = shap.LinearExplainer(est, Xt)
            sv = expl.shap_values(Xt)
        else:
            expl = shap.TreeExplainer(est)
            sv = expl.shap_values(Xt)
        sv = np.asarray(sv)
        if sv.ndim == 3:  # (n, features, classes) or (classes, n, features)
            sv = sv[..., 1] if sv.shape[-1] == 2 else sv[1]
        mean_abs = np.abs(sv).mean(axis=0)
        fig = plt.figure(figsize=(8, 7))
        shap.summary_plot(sv, Xt, feature_names=[C.FEATURE_LABELS[f] for f in C.FEATURES],
                          show=False, max_display=15)
        path = fig_to_file(plt.gcf(), "shap_summary.png")
        return dict(sorted(zip(C.FEATURES, map(float, mean_abs)), key=lambda kv: -kv[1])), path
    except Exception as exc:  # pragma: no cover
        print(f"[warn] SHAP skipped: {exc}")
        return None, None


def main(register: bool = True) -> dict:
    X, y, ids = load_xy()
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=C.TEST_SIZE,
                                              stratify=y, random_state=C.RANDOM_SEED)
    pos_weight = float((y_tr == 0).sum() / max((y_tr == 1).sum(), 1))
    cv = StratifiedKFold(C.CV_FOLDS, shuffle=True, random_state=C.RANDOM_SEED)

    tracking.setup(C.MLFLOW_EXPERIMENT)
    client = MlflowClient()

    candidates = M.make_candidates(pos_weight)
    results, fitted = {}, {}

    with mlflow.start_run(run_name=f"training-{datetime.now():%Y%m%d-%H%M%S}") as parent:
        mlflow.log_params({
            "dataset_rows": len(X), "n_features": len(C.FEATURES), "target": C.TARGET,
            "pass_mark": C.PASS_MARK, "test_size": C.TEST_SIZE, "cv_folds": C.CV_FOLDS,
            "seed": C.RANDOM_SEED, "train_positive_rate": round(float(y_tr.mean()), 4),
            "xgboost_available": M.HAVE_XGB, "sklearn": sklearn.__version__,
            "python": platform.python_version(),
        })
        mlflow.log_artifact(str(C.ML_DATASET_META), artifact_path="data")

        # ---- baselines -------------------------------------------------------
        base = {}
        majority = M.make_baselines()["baseline_majority"].fit(X_tr, y_tr)
        base["baseline_majority"] = M.metrics_at(y_te, majority.predict_proba(X_te)[:, 1])
        base["baseline_rule_G2_below_10"] = M.metrics_at(y_te, M.rule_baseline_scores(X_te), 0.5)
        for name, m in base.items():
            with mlflow.start_run(run_name=name, nested=True):
                mlflow.log_param("model_type", name)
                mlflow.log_metrics({f"test_{k}": v for k, v in m.items() if k not in ("tn", "fp", "fn", "tp", "threshold")})

        # ---- candidates ------------------------------------------------------
        for name, pipe in candidates.items():
            cvr = cross_validate(pipe, X_tr, y_tr, cv=cv, n_jobs=1,
                                 scoring={"roc_auc": "roc_auc", "pr_auc": "average_precision",
                                          "recall": "recall", "f1": "f1"})
            cv_sum = {f"cv_{k}_mean": float(cvr[f"test_{k}"].mean()) for k in ("roc_auc", "pr_auc", "recall", "f1")}
            cv_sum["cv_roc_auc_std"] = float(cvr["test_roc_auc"].std())
            model = clone(pipe).fit(X_tr, y_tr)
            proba_te = model.predict_proba(X_te)[:, 1]
            te = M.metrics_at(y_te, proba_te)
            results[name] = {"cv": cv_sum, "test": te}
            fitted[name] = model

            with mlflow.start_run(run_name=name, nested=True) as child:
                clf = pipe[-1]
                mlflow.log_param("model_type", type(clf).__name__)
                mlflow.log_params({f"hp_{k}": v for k, v in clf.get_params().items()
                                   if isinstance(v, (int, float, str, bool, type(None)))})
                mlflow.log_metrics(cv_sum)
                mlflow.log_metrics({f"test_{k}": v for k, v in te.items() if k not in ("tn", "fp", "fn", "tp", "threshold")})
                sig = infer_signature(X_tr, model.predict_proba(X_tr.head(50)))
                info = mlflow.sklearn.log_model(model, name="model", signature=sig,
                                                input_example=X_tr.head(3),
                                                serialization_format="cloudpickle")
                results[name]["run_id"] = child.info.run_id
                results[name]["model_uri"] = info.model_uri
            print(f"{name:22s} CV AUC {cv_sum['cv_roc_auc_mean']:.3f}±{cv_sum['cv_roc_auc_std']:.3f} | "
                  f"test AUC {te['roc_auc']:.3f} PR-AUC {te['pr_auc']:.3f} recall {te['recall']:.2f}")

        # ---- select winner by CV (never by the test set) -----------------------
        winner = max(results, key=lambda n: results[n]["cv"]["cv_roc_auc_mean"])
        model = fitted[winner]
        oof = cross_val_predict(clone(candidates[winner]), X_tr, y_tr, cv=cv, method="predict_proba")[:, 1]
        threshold = M.pick_threshold(y_tr, oof, min_recall=0.80)
        proba_te = model.predict_proba(X_te)[:, 1]
        test_default = M.metrics_at(y_te, proba_te, 0.5)
        test_tuned = M.metrics_at(y_te, proba_te, threshold)
        print(f"\nWinner: {winner} | operating threshold {threshold} (OOF recall>=0.80) | "
              f"test recall {test_tuned['recall']:.2f} precision {test_tuned['precision']:.2f}")

        # ---- plots -------------------------------------------------------------
        fig, ax = plt.subplots(figsize=(5.5, 4.5))
        for n, mdl in fitted.items():
            RocCurveDisplay.from_predictions(y_te, mdl.predict_proba(X_te)[:, 1], name=n, ax=ax)
        ax.plot([0, 1], [0, 1], "k--", lw=0.8); ax.set_title("ROC curves (held-out test set)")
        roc_path = fig_to_file(fig, "roc_curves.png")
        fig, ax = plt.subplots(figsize=(5.5, 4.5))
        PrecisionRecallDisplay.from_predictions(y_te, proba_te, name=winner, ax=ax)
        ax.set_title("Precision-recall (winner)")
        pr_path = fig_to_file(fig, "pr_curve.png")
        fig, ax = plt.subplots(figsize=(4.5, 4))
        ConfusionMatrixDisplay.from_predictions(y_te, (proba_te >= threshold).astype(int), ax=ax,
                                                display_labels=["Not at risk", "At risk"], colorbar=False)
        ax.set_title(f"Confusion matrix @ threshold {threshold}")
        cm_path = fig_to_file(fig, "confusion_matrix.png")
        shap_imp, shap_path = shap_summary(model, X_te)

        # ---- log winner summary on the parent run --------------------------------
        mlflow.set_tags({"winner": winner, "selection_metric": "cv_roc_auc_mean"})
        mlflow.log_params({"winner": winner, "operating_threshold": threshold})
        mlflow.log_metrics({f"winner_test_{k}": v for k, v in test_default.items() if k not in ("tn", "fp", "fn", "tp", "threshold")})
        mlflow.log_metrics({"winner_tuned_recall": test_tuned["recall"], "winner_tuned_precision": test_tuned["precision"],
                            "winner_tuned_f1": test_tuned["f1"]})
        for p in (roc_path, pr_path, cm_path, shap_path):
            if p:
                mlflow.log_artifact(str(p), artifact_path="plots")
        if shap_imp:
            mlflow.log_dict(shap_imp, "plots/shap_mean_abs.json")

        # ---- registry: champion / challenger ---------------------------------------
        promoted, reg_version, prev_auc = None, None, None
        if register:
            reg = mlflow.register_model(results[winner]["model_uri"], C.REGISTERED_MODEL_NAME)
            reg_version = int(reg.version)
            client.set_model_version_tag(C.REGISTERED_MODEL_NAME, reg.version, "algorithm", winner)
            client.set_model_version_tag(C.REGISTERED_MODEL_NAME, reg.version, "test_roc_auc",
                                         f"{test_default['roc_auc']:.4f}")
            try:
                champ = client.get_model_version_by_alias(C.REGISTERED_MODEL_NAME, C.CHAMPION_ALIAS)
                prev_auc = float(champ.tags.get("test_roc_auc", "nan"))
            except Exception:
                champ = None
            if champ is None or np.isnan(prev_auc) or test_default["roc_auc"] >= prev_auc - PROMOTION_TOLERANCE:
                client.set_registered_model_alias(C.REGISTERED_MODEL_NAME, C.CHAMPION_ALIAS, reg.version)
                promoted = True
                print(f"Registry: version {reg_version} promoted to alias '{C.CHAMPION_ALIAS}'"
                      + ("" if champ is None else f" (previous champion v{champ.version} AUC {prev_auc:.3f})"))
            else:
                promoted = False
                print(f"Registry: version {reg_version} NOT promoted (test AUC {test_default['roc_auc']:.3f} "
                      f"< champion {prev_auc:.3f} - {PROMOTION_TOLERANCE})")
            mlflow.set_tags({"registered_version": str(reg_version), "promoted": str(promoted)})

        # ---- export serving bundle (only if this model is / stays the champion) -------
        if promoted in (True, None):
            C.MODEL_DIR.mkdir(parents=True, exist_ok=True)
            meta = {
                "model_name": C.REGISTERED_MODEL_NAME, "algorithm": winner,
                "registry_version": reg_version, "alias": C.CHAMPION_ALIAS if promoted else None,
                "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "mlflow_run_id": parent.info.run_id, "threshold": threshold,
                "features": C.FEATURES, "target": C.TARGET,
                "target_definition": f"final score G3 < {C.PASS_MARK}",
                "metrics_test_default_threshold": test_default,
                "metrics_test_operating_threshold": test_tuned,
                "cv": results[winner]["cv"], "all_models": {n: {"cv": r["cv"], "test": r["test"]} for n, r in results.items()},
                "baselines": base, "shap_mean_abs": shap_imp,
                "env": {"sklearn": sklearn.__version__, "python": platform.python_version(),
                        "pandas": pd.__version__, "numpy": np.__version__},
            }
            joblib.dump(model, C.CHAMPION_PATH)
            C.CHAMPION_META.write_text(json.dumps(meta, indent=2))
            C.REFERENCE_STATS.write_text(json.dumps(
                build_reference_stats(X_tr, y_tr, test_tuned), indent=2))
            mlflow.log_artifact(str(C.CHAMPION_META), artifact_path="serving_bundle")
            print(f"Exported serving bundle -> {C.MODEL_DIR}")

        # summary table for the report
        rows = [{"model": n, **{f"cv_{k}": r["cv"][f"cv_{k}_mean"] for k in ("roc_auc", "pr_auc", "recall", "f1")},
                 "cv_roc_auc_std": r["cv"]["cv_roc_auc_std"],
                 **{f"test_{k}": r["test"][k] for k in ("roc_auc", "pr_auc", "precision", "recall", "f1")}}
                for n, r in results.items()]
        for n, m in base.items():
            rows.append({"model": n, **{f"test_{k}": m[k] for k in ("roc_auc", "pr_auc", "precision", "recall", "f1")}})
        pd.DataFrame(rows).round(4).to_csv(C.REPORT_DIR / "model_comparison.csv", index=False)
        mlflow.log_artifact(str(C.REPORT_DIR / "model_comparison.csv"))

    return {"winner": winner, "threshold": threshold, "test": test_default, "tuned": test_tuned,
            "promoted": promoted, "version": reg_version}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-register", action="store_true", help="track runs but skip the model registry")
    args = ap.parse_args()
    main(register=not args.no_register)
