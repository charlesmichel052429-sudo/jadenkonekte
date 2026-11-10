# Application Jaden Konekté : API, ingestion MQTT, règles d'arrosage et interface web
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY app/requirements.txt .
RUN pip install --no-cache-dir --default-timeout=120 --retries 10 -r requirements.txt
COPY infra/sql/schema.sql /app/sql/schema.sql
COPY openapi.yaml /app/openapi.yaml
COPY ia/cnn/classes_fr.json /app/classes_fr.json
COPY ia/rag/fiches /app/fiches
COPY ia/rag/questions_reference.json /app/questions_reference.json
COPY app/pytest.ini /app/pytest.ini
COPY app/jaden /app/jaden
COPY app/web /app/web
COPY app/tests /app/tests
# Chart.js est intégré à l'image : l'interface ne dépend d'aucun site externe
ADD https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js /app/web/vendor/chart.umd.min.js
RUN chmod 644 /app/web/vendor/chart.umd.min.js && mkdir -p /donnees/diagnostics && chown -R 1000:1000 /donnees
USER 1000
CMD ["uvicorn", "jaden.main:app", "--host", "0.0.0.0", "--port", "8000"]
