"""MLflow setup shared by training and monitoring."""

import mlflow

from mlops import config as C


def setup(experiment: str) -> None:
    """Point MLflow at the configured store and select (or create) the experiment.

    For the default local SQLite store the artifacts are kept in mlstore/artifacts
    so the whole store lives in one folder. For a remote server (e.g. DagsHub) the
    server decides where artifacts go, so we only select the experiment."""
    mlflow.set_tracking_uri(C.MLFLOW_TRACKING_URI)
    if C.MLFLOW_TRACKING_URI.startswith("sqlite:"):
        C.MLSTORE_DIR.mkdir(parents=True, exist_ok=True)
        if mlflow.get_experiment_by_name(experiment) is None:
            mlflow.create_experiment(experiment, artifact_location=(C.MLSTORE_DIR / "artifacts" / experiment).as_uri())
    mlflow.set_experiment(experiment)
