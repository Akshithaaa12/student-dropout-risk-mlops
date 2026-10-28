# ML design (Part 2)

## Problem
Predict, at mid-semester, which students are on course to fail a subject so a mentor can step in.

**Target (`at_risk`)**: 1 if the final score `G3 < 10` (the dataset's own pass mark), else 0.
The UCI data has no literal "dropped out" field, so this is a **proxy** for dropout risk. 22.1% of the
1,034 student-subject records are positive.

## Prediction time and leakage control
Predictions are made after the second assessment (G2) but before the final result (G3).

| Excluded | Why |
|---|---|
| `current_score` / `G3`, `pass_flag` | They *are* the target |
| `risk_score`, `risk_category` | Part 1's rule-based score is computed from the final score |
| `department`, `semester` | Randomly assigned in Part 1 (synthetic), no real signal |
| `student_id` | Identifier |

30 features are used: 5 from the multi-source mart (attendance, internal marks, G2, assignment completion, LMS
engagement), 18 numeric and 7+2 binary fields from the real academic record, and the 3 Part 1 `*_data_available`
flags. The contract lives in `mlops/config.py` and is shared by training, API, monitoring and dashboard.
`tests/test_dataset_and_model.py` asserts no banned column can enter.

## Missing values
The Part 1 mart is already complete (documented fallbacks + flags). At serving time a missing optional field is
imputed with the **training median** inside the model pipeline, and the matching availability flag is set to 0.
This is the "justified imputation for ML" case in the course guideline; the flag columns stay in the model so it
can learn from missingness itself.

## Evaluation protocol
Stratified 80/20 split (seed 42: 827 train / 207 test, 46 positives in test) -> 5-fold stratified CV on the
train split for every candidate -> winner chosen by **CV ROC-AUC** -> test set scored once for the report.
Operating threshold is chosen on out-of-fold train predictions as the highest value that keeps recall >= 0.80
(a missed at-risk student costs more than an extra check-in).

## Candidates and baselines
| Model | Notes |
|---|---|
| Majority class | floor: ROC-AUC 0.50 |
| Rule "G2 < 10" | what an advisor would do without ML |
| Logistic Regression | scaled, `class_weight=balanced`, interpretable |
| Random Forest | 300 trees, `min_samples_leaf=3`, balanced subsample |
| Gradient Boosting (sklearn HistGB) | depth 3, 250 iterations, lr 0.05, balanced class weights; no native library needed |
| SVM (RBF kernel) | scaled inputs, `class_weight=balanced`, probabilities via sigmoid calibration (5-fold); a different model family |
| XGBoost | depth 3, 250 trees, lr 0.05, `scale_pos_weight` (skipped automatically if XGBoost cannot load) |

Hyperparameters are fixed, not tuned (sensible defaults for ~800 rows). Tuning is listed under limitations.

## Results (seed 42; re-run `python -m mlops.train` to reproduce)
| Model | CV ROC-AUC | Test ROC-AUC | Test PR-AUC | Test recall | Test precision |
|---|---|---|---|---|---|
| Logistic Regression | 0.969 | 0.964 | 0.907 | 0.91 | 0.66 |
| **Random Forest (champion)** | **0.971** | 0.968 | 0.903 | 0.89 | 0.71 |
| Gradient Boosting (HistGB) | 0.959 | 0.972 | 0.923 | 0.87 | 0.68 |
| SVM (RBF) | 0.954 | 0.957 | 0.881 | 0.78 | 0.80 |
| XGBoost | 0.963 | 0.974 | 0.927 | 0.89 | 0.71 |
| Rule "G2 < 10" | n/a | 0.971 | 0.894 | 1.00 | 0.53 |
| Majority class | n/a | 0.500 | 0.222 | 0.00 | 0.00 |

Test recall/precision above use the default 0.5 threshold. At the champion's operating threshold (0.64) the test
confusion matrix is TN 150, FP 11, FN 8, TP 38 (recall 0.83, precision 0.78, F1 0.80).

## What the results do and do not say
* All five models are statistically indistinguishable on 207 test rows (only 46 positives); Random Forest won on CV,
  XGBoost has the best single test AUC. Selection used CV only, so the test number is not inflated by choosing.
* **The simple rule "G2 < 10" already reaches ROC-AUC 0.971.** G2 is a very strong predictor of G3. The models'
  real gain is fewer false alarms: at the default threshold they flag 17 students wrongly versus 40 for the rule,
  while missing 5 at-risk students versus 0 for the rule. That trade-off, not AUC, is the honest case for ML here.
* SHAP shows the model leans on `avg_internal_marks` and `previous_semester_score` (derived from G1/G2), then
  `failures`. The synthetic ERP/LMS/assignment features contribute little, which is expected because they were
  generated independently of G3 (documented in Part 1). Attendance and LMS only matter in a real deployment.
* Early-warning use only: a flag starts a conversation, it does not decide anything about a student.

## Limitations
Proxy label, ~1k rows from two schools, synthetic enrichment sources, no hyperparameter search, no probability
calibration step beyond the Brier score (0.071), no fairness audit across groups (sex is a feature; see below).
`is_male` has near-zero SHAP importance, but a real deployment would need an explicit fairness review before use.

## Experiment tracking and registry
MLflow (SQLite store in `mlstore/`, or DagsHub via env vars). One parent run per training with one child run per
model plus the two baselines; params, CV + test metrics, ROC/PR/confusion/SHAP plots, signature and input example
are logged. The winner is registered as `student-dropout-risk`. **Promotion rule:** a new version takes the
`champion` alias if its test ROC-AUC is >= the current champion's minus 0.005; otherwise it stays unpromoted and the
serving bundle is left alone. (Seen working: a second identical run created v2 and moved the alias from v1.)
