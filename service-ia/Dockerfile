# Service d'inférence : ONNX Runtime sur CPU (diagnostic des feuilles et embeddings)
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=120 --retries 10 -r requirements.txt
# Modèle d'embeddings multilingue (version quantifiée) intégré à l'image
ADD https://huggingface.co/Xenova/paraphrase-multilingual-MiniLM-L12-v2/resolve/main/onnx/model_quantized.onnx /embeddings/model.onnx
ADD https://huggingface.co/Xenova/paraphrase-multilingual-MiniLM-L12-v2/resolve/main/tokenizer.json /embeddings/tokenizer.json
RUN chmod -R a+r /embeddings
COPY ia_service /app/ia_service
COPY tests /app/tests
USER 1000
CMD ["uvicorn", "ia_service.service:app", "--host", "0.0.0.0", "--port", "8000"]
