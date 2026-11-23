# App image: builds the React frontend, then serves it and the API with FastAPI.

FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SALES_CSV=/app/data/sales.csv \
    DB_PATH=/app/var/sales.db \
    FRONTEND_DIST=/app/frontend/dist \
    RECIPIENTS_CSV=/app/config/recipients.csv
WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY data/ /app/data/
COPY --from=web /web/dist /app/frontend/dist
RUN useradd --create-home app && mkdir -p /app/var && chown app /app/var
USER app
EXPOSE 8000
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
