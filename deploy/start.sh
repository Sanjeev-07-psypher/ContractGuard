#!/bin/sh
# Start the API on localhost and the Streamlit UI on $PORT (7860 on Hugging Face Spaces).
# The UI calls the API server-side, so only the UI port is exposed.
set -e
PORT="${PORT:-7860}"

uvicorn backend.main:app --host 127.0.0.1 --port 8000 &
API_PID=$!

# Wait until the API answers (models load at startup), at most about 3 minutes.
i=0
until curl -fs http://127.0.0.1:8000/api/v1/health > /dev/null; do
  i=$((i + 1))
  if [ "$i" -gt 90 ] || ! kill -0 "$API_PID" 2> /dev/null; then
    echo "API did not start" >&2
    exit 1
  fi
  sleep 2
done

exec streamlit run frontend/app.py \
  --server.port "$PORT" --server.address 0.0.0.0 --server.headless true \
  --server.enableCORS false --server.enableXsrfProtection false \
  --browser.gatherUsageStats false --client.toolbarMode minimal
