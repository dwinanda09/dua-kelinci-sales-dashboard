# Backend image (FastAPI). The frontend has its own image: frontend/Dockerfile.
#   runtime (default): the API, run by the `app` service
#   test:              the backend unit tests, run by `make test`

FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SALES_CSV=/app/data/sales.csv \
    DB_PATH=/app/var/sales.db \
    RECIPIENTS_CSV=/app/config/recipients.csv
WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM base AS test
COPY backend/requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY backend/ .
COPY data/ /app/data/
CMD ["pytest"]

FROM base AS runtime
COPY backend/ .
COPY data/ /app/data/
RUN useradd --create-home app && mkdir -p /app/var && chown app /app/var
USER app
EXPOSE 8000
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
