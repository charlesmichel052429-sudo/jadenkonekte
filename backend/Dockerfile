# Image commune aux services Python de la plateforme (api, ingestion, règles) ; contexte = racine du dépôt
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY infra/sql/schema.sql /app/sql/schema.sql
COPY openapi.yaml /app/openapi.yaml
COPY ia/cnn/classes_fr.json /app/classes_fr.json
# Volume des photos de diagnostic : créé avec le bon propriétaire (le service tourne sans privilèges)
RUN mkdir -p /donnees/diagnostics && chown -R 1000:1000 /donnees
COPY backend/pytest.ini /app/pytest.ini
COPY backend/jaden /app/jaden
COPY backend/tests /app/tests
USER 1000
CMD ["uvicorn", "jaden.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
