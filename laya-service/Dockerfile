FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 HF_HOME=/tmp/huggingface
WORKDIR /app
# CPU-only PyTorch avoids downloading CUDA libraries on a CPU VPS.
RUN pip install --no-cache-dir torch==2.8.0 --index-url https://download.pytorch.org/whl/cpu && pip install --no-cache-dir laya==0.3.26 transformers==4.57.1 protobuf==6.32.1 fastapi==0.142.2 uvicorn==0.54.0 && useradd --uid 10001 --create-home keno
COPY server.py entrypoint.sh ./
RUN chmod 0555 /app/entrypoint.sh
USER keno
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
ENTRYPOINT ["/app/entrypoint.sh"]
