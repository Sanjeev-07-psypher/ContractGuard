# ContractGuard: FastAPI backend + Streamlit UI in one image (Hugging Face Spaces, Docker SDK).
# Build:  docker build -t contractguard .
# Run:    docker run -p 7860:7860 contractguard   then open http://localhost:7860
FROM ubuntu:24.04

ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Optional extra CA certificates (*.crt) for builds behind a TLS-inspecting proxy.
# The folder is empty in the repository.
COPY deploy/certs/ /usr/local/share/ca-certificates/
RUN apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates curl python3 python3-venv tesseract-ocr tesseract-ocr-eng \
 && update-ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && python3 -m venv /opt/venv

ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt

# Hugging Face Spaces runs the container as user 1000 (the Ubuntu image's default user).
RUN userdel -r ubuntu 2>/dev/null; useradd -m -u 1000 user
WORKDIR /app

COPY deploy/requirements.txt deploy/requirements.txt
RUN pip install torch --index-url "$TORCH_INDEX_URL" \
 && pip install -r deploy/requirements.txt

ENV HOME=/home/user \
    HF_HOME=/home/user/.cache/huggingface \
    PYTHONPATH=/app \
    CG_API_URL=http://127.0.0.1:8000/api/v1

# Download the MiniLM embedding model at build time so the app starts without the network.
# If the download fails, the app still runs: semantic checks are skipped with a warning.
USER user
RUN python -c "from sentence_transformers import SentenceTransformer as S; S('sentence-transformers/all-MiniLM-L6-v2', device='cpu')" \
 || echo "MiniLM not downloaded; semantic checks will be skipped"
USER root

COPY --chown=user:user . /app
RUN mkdir -p /app/data && chown -R user:user /app

USER user
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s \
  CMD curl -fs http://127.0.0.1:8000/api/v1/health || exit 1
CMD ["sh", "deploy/start.sh"]
