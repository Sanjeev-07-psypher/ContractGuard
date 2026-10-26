"""Home page: what ContractGuard does and whether the backend, models and OCR are ready."""

from __future__ import annotations

import streamlit as st

from frontend import api_client, ui  # noqa: F401  (ui sets sys.path first)

ui.page("ContractGuard", "🛡️")
st.markdown(
    "Upload a contract (PDF, scanned PDF or DOCX). ContractGuard splits it into clauses, "
    "classifies them, checks them against your policy and explains every flag with the clause "
    "text it is based on."
)

try:
    h = api_client.health()
except api_client.APIError as exc:
    ui.show_error(exc)
    st.stop()

cols = st.columns(4)
cols[0].metric("Backend", "Online" if h["status"] == "ok" else "Degraded")
cols[1].metric("Models", "Loaded" if h["models_loaded"] else "Not loaded")
cols[2].metric("OCR (Tesseract)", "Available" if h["tesseract_available"] else "Missing")
cols[3].metric(
    "AI explanations",
    h["llm_provider"].title() if h["llm_provider"] != "none" else "Templates",
)
if h.get("error"):
    st.warning(h["error"])
if not h.get("embeddings_loaded", True):
    st.info("Embedding model not loaded: semantic cross-checks are skipped.")

st.page_link("pages/1_Upload.py", label="Upload & Analyze", icon="⬆️")
st.page_link("pages/2_Report.py", label="Report Dashboard", icon="📊")
st.page_link("pages/3_Clauses.py", label="Clause Explorer", icon="🔎")
st.page_link("pages/4_Policy.py", label="Policy Editor", icon="⚙️")
