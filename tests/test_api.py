import pytest
from fastapi.testclient import TestClient

from api import main


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PREDICTION_LOG", str(tmp_path / "pred.csv"))
    with TestClient(main.app) as c:
        yield c


def test_health_and_info(client):
    r = client.get("/health").json()
    assert r["status"] == "ok" and r["model_loaded"] is True
    info = client.get("/model-info").json()
    assert info["algorithm"] and len(info["features"]) == 30


def test_low_vs_high_risk_ordering(client):
    low = client.post("/predict", json={"previous_semester_score": 17, "avg_internal_marks": 16.5, "failures": 0}).json()
    high = client.post("/predict", json={"previous_semester_score": 6, "avg_internal_marks": 6.5, "failures": 2}).json()
    assert 0 <= low["at_risk_probability"] <= 1
    assert high["at_risk_probability"] > low["at_risk_probability"]
    assert high["at_risk"] is True and low["at_risk"] is False
    assert high["top_factors"]


def test_missing_optional_fields_are_ok(client):
    r = client.post("/predict", json={"previous_semester_score": 12})
    assert r.status_code == 200


def test_validation_rejects_bad_input(client):
    assert client.post("/predict", json={"previous_semester_score": 25}).status_code == 422
    assert client.post("/predict", json={"avg_internal_marks": 10}).status_code == 422  # required field missing
    assert client.post("/predict", json={"previous_semester_score": 10, "bogus": 1}).status_code == 422


def test_batch_and_logging(client, tmp_path):
    body = {"students": [{"student_id": "A", "previous_semester_score": 8},
                         {"student_id": "B", "previous_semester_score": 15}]}
    r = client.post("/predict/batch", json=body).json()
    assert r["count"] == 2
    log = (tmp_path / "pred.csv").read_text().splitlines()
    assert len(log) == 3  # header + 2 rows
    assert client.get("/stats").json()["predictions"] >= 2
