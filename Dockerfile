# One image, three jobs (selected by the command in docker-compose.yml):
#   api      -> uvicorn api.main:app            (model serving)
#   trainer  -> python -m mlops.train           (retrain inside the SAME library versions)
#   mlflow   -> mlflow server / ui              (experiment + registry UI)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MLFLOW_DISABLE_AGENT_HINT=1

# libgomp1 is required by xgboost / scikit-learn's OpenMP code on Debian slim
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements-docker.txt .
RUN pip install --no-cache-dir --default-timeout=120 --retries 10 -r requirements-docker.txt

# Code only. Data, trained models, logs and the MLflow store are mounted as volumes
# (see docker-compose.yml) so rebuilding the image never wipes them.
COPY mlops/ ./mlops/
COPY api/ ./api/
COPY scripts/ ./scripts/

RUN useradd --create-home appuser && mkdir -p /app/models /app/logs /app/data /app/reports \
    && chown -R appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
