# Monitoring and retraining policy (Part 2)

`python -m mlops.monitoring` compares what the API has scored (`logs/prediction_log.csv`, one row per prediction)
against the training snapshot in `models/reference_stats.json` (10 quantile bins per continuous feature, category
shares for discrete ones, a 400-point sample for KS tests).

## Signals
| Signal | Method | Thresholds |
|---|---|---|
| Data drift | Population Stability Index per feature (+ KS test for continuous) | PSI 0.10 watch, 0.20 warning, 0.25 drift |
| Prediction drift | Share flagged at-risk vs reference share on the test set (23.7%) | shift > 10 percentage points |
| Missing-data drift | Share of requests with each `*_data_available` flag = 0 | reported, no trigger |
| Performance drift | Recall and ROC-AUC on logged students whose outcome is known (`data/ml/outcomes.csv`: `student_id, at_risk_actual`) | recall < 0.70 or AUC down > 0.05 |
| Model age | days since `trained_at` | > 180 days |

A check needs at least 30 logged predictions, otherwise the report says `insufficient_data` rather than guess.

## Retraining triggers
* **T1** 2 or more features with PSI > 0.20, or any feature with PSI > 0.25
* **T2** flagged share shifts by more than 10 pp
* **T3** performance decay (only once labels exist; final marks arrive at semester end)
* **T4** model older than one academic semester (180 days)

Any trigger gives status `RETRAIN_RECOMMENDED`. `--retrain` then runs `mlops.train`, which registers a challenger
and applies the promotion rule in `docs/ml_design.md`. Retraining is a recommendation to a human, not an
automatic deploy: someone checks the new metrics in the MLflow registry first. Each check is also logged to the
MLflow experiment `student-dropout-risk-monitoring`.

## Evidence
* Real-traffic path: a 300-row unshifted sample scores `healthy` (unit test `test_unshifted_batch_is_healthy`).
  Caveat: that sample is drawn from the training pool, so it demonstrates the mechanism, not field behaviour.
* Drift demo: `--simulate-drift` fabricates a bad semester (attendance -14 pts, LMS -18, G2 -2, absences +5) on real
  rows. Result: status RETRAIN_RECOMMENDED, T1 (5 features PSI > 0.2, attendance 4.2) and T2 (+25 pp flagged).
  The report is labelled SIMULATED everywhere; no real drift has been observed because there is no production traffic.

## Not covered
No alerting channel (email/Slack) is wired up, no scheduled run outside the Airflow DAG, and the monitor does not
yet track latency or error rates beyond the in-memory `/stats` endpoint.
