FROM python:3.11-slim

# FFmpeg trengs for lyd-/videobehandling
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Pin HuggingFace-cache til en fast sti (matcher volumet i docker-compose)
ENV HF_HOME=/cache/huggingface
RUN mkdir -p /cache/huggingface

COPY requirements.txt .
# CPU-only torch (containeren har ikke GPU) – unngår flere GB med CUDA-bibliotek
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p uploads output

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=4).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
