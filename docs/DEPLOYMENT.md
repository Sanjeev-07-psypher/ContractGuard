# Deployment

ContractGuard ships as one Docker image that runs the FastAPI backend on `127.0.0.1:8000` and the
Streamlit UI on port 7860. The UI talks to the API inside the container, so only port 7860 is
exposed. The public demo runs on a free Hugging Face Space (Docker SDK).

## What is in the image

| Part | Source |
|---|---|
| Ubuntu 24.04, Python 3.12, Tesseract 5 (English) | `apt` |
| Python packages, pinned to the tested versions | `deploy/requirements.txt` |
| PyTorch, CPU-only wheel | `download.pytorch.org/whl/cpu` (build argument `TORCH_INDEX_URL`) |
| spaCy `en_core_web_sm` | GitHub release wheel |
| MiniLM embedding model | downloaded at build time; if that fails, the app runs without semantic checks |
| Trained classifier, thresholds, prototypes | `models/` (committed; the classifier is xz-compressed to 8.5 MB, D53) |
| Code, config, policies | the repository |

`deploy/start.sh` starts uvicorn, waits until `/api/v1/health` answers, then starts Streamlit.
The container runs as user 1000, which Hugging Face Spaces requires.

## Run it locally

```bash
docker build -t contractguard .
docker run -p 7860:7860 contractguard
# open http://localhost:7860
```

Optional AI explanations: add `-e LLM_PROVIDER=gemini -e LLM_MODEL=<model> -e GEMINI_API_KEY=<key>`
to `docker run`, or point at a local Ollama with `-e LLM_PROVIDER=ollama -e LLM_MODEL=qwen2.5:3b
-e CG_LLM__OLLAMA_HOST=http://host.docker.internal:11434`. Never put a key in the Dockerfile.

## Hugging Face Space (automatic)

`.github/workflows/deploy-space.yml` uploads the files the image needs to the Space on every push
to `main` (and on demand from the Actions tab). The Space then rebuilds the image itself.

One-time setup:

1. Create a free Hugging Face account and a Space: SDK **Docker**, template **Blank**, hardware
   **CPU basic**.
2. Create a Hugging Face access token with the **Write** role.
3. In the GitHub repository, **Settings → Secrets and variables → Actions**: add the secret
   `HF_TOKEN` (the token) and the variable `HF_SPACE` (`username/space-name`).
4. Optional, in the Space's **Settings → Variables and secrets**: the secret `GEMINI_API_KEY` and
   the variable `LLM_MODEL`. Without them, explanations use templates.

The upload uses `huggingface_hub.HfApi.upload_folder`, which stores binary files (the model and
the PDFs) the way the Hub requires. The Space card comes from `deploy/huggingface/README.md`.

## Limits of the free demo

- 2 vCPU and 16 GB RAM: a text PDF takes about a second; a scanned page takes a few seconds of
  OCR. Gemini calls are paced at 8 per minute (`llm.rpm`).
- No persistent disk: uploads, reports and edited policies are lost when the Space restarts or
  sleeps after inactivity.
- No login: every visitor sees the same contract list. Use synthetic or public contracts only.
- With Gemini on the free tier, Google may use the clauses sent to it.

## Verified

The image was built and run in the development environment on 2026-11-08: `/health` reported
models loaded and Tesseract available, the UI answered on its port, and the gold contracts GC01
(scanned PDF, 4 OCR pages, about 11 s) and GC03 (DOCX, under 1 s) produced the expected
findings through the API, and all 308 tests passed inside the image on Python 3.12. MiniLM could not be downloaded there (network policy), so that run had
no semantic checks; on Hugging Face the model downloads at build time.

## Behind a TLS-inspecting proxy

Put the proxy's CA certificates as `*.crt` files in `deploy/certs/` (git-ignored) before building,
and pass the proxy as build arguments (`--build-arg https_proxy=...`).
