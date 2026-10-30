# Service d'inférence du CNN (ONNX Runtime, CPU) — indépendant de l'API
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=120 --retries 10 -r requirements.txt
COPY diagnostic /app/diagnostic
COPY tests /app/tests
COPY pytest.ini /app/pytest.ini
USER 1000
CMD ["uvicorn", "diagnostic.service:app", "--host", "0.0.0.0", "--port", "8000"]
