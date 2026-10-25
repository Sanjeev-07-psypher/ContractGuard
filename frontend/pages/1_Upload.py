"""Upload & Analyze (HLD 11.1)."""

from __future__ import annotations

import time

import streamlit as st

from frontend import api_client, ui

ui.page("Upload & Analyze", "⬆️")
settings_poll = api_client.get_settings().frontend.poll_seconds
STAGES = {
    "QUEUED": "Queued",
    "EXTRACTING": "Reading the file (OCR if scanned)",
    "SEGMENTING": "Finding clauses",
    "CLASSIFYING": "Classifying clauses",
    "EVALUATING": "Checking the policy",
    "EXPLAINING": "Writing explanations",
    "DONE": "Done",
    "FAILED": "Failed",
}

try:
    policies = api_client.policies()
except api_client.APIError as exc:
    ui.show_error(exc)
    st.stop()

with st.form("upload"):
    file = st.file_uploader(
        "Contract file",
        type=["pdf", "docx"],
        help="Text PDF, scanned PDF or DOCX, up to 20 MB / 60 pages.",
    )
    c1, c2 = st.columns(2)
    ctype = c1.selectbox(
        "Contract type", list(ui.CONTRACT_TYPES), format_func=ui.CONTRACT_TYPES.__getitem__
    )
    org = c2.text_input(
        "Your organization name",
        value=api_client.get_settings().org.default_name,
        help="Used to tell which party is yours (e.g. for NDAs).",
    )
    c3, c4 = st.columns(2)
    policy_id = c3.selectbox(
        "Policy",
        [p["policy_id"] for p in policies],
        format_func=lambda pid: next(
            f"{p['name']} (v{p['version']})" for p in policies if p["policy_id"] == pid
        ),
    )
    use_llm = c4.toggle(
        "Use AI explanations",
        value=True,
        help="Off: deterministic template explanations only. Only the flagged "
        "clause is ever sent to the AI provider.",
    )
    submitted = st.form_submit_button("Analyze", type="primary", use_container_width=True)

if submitted:
    if file is None:
        st.warning("Choose a PDF or DOCX file first.")
        st.stop()
    try:
        job = api_client.upload(file.name, file.getvalue(), ctype, org, policy_id, use_llm)
    except api_client.APIError as exc:
        ui.show_error(exc)
        st.stop()
    cid = job["contract_id"]
    bar = st.progress(0, text=STAGES["QUEUED"])
    while True:
        s = api_client.status(cid)
        bar.progress(int(s["progress"]), text=STAGES.get(s["stage"], s["stage"]))
        if s["status"] in ("DONE", "FAILED"):
            break
        time.sleep(settings_poll)
    if s["status"] == "FAILED":
        st.error(f"Analysis failed: {s['error']}")
        st.stop()
    st.session_state["contract_id"] = cid
    st.success("Analysis complete.")
    st.switch_page("pages/2_Report.py")

st.subheader("Recent analyses")
try:
    rows = api_client.contracts()
except api_client.APIError as exc:
    ui.show_error(exc)
    st.stop()
if not rows:
    st.caption("Nothing analysed yet.")
for r in rows:
    counts = r.get("counts") or {}
    c1, c2, c3 = st.columns([5, 3, 1])
    c1.markdown(
        f"**{r['filename']}**  \n<span class='cg-muted'>{r['created_at'][:16].replace('T', ' ')}"
        f" · {r['status']}</span>",
        unsafe_allow_html=True,
    )
    if counts:
        c2.markdown(
            f"HIGH {counts.get('HIGH', 0)} · MEDIUM {counts.get('MEDIUM', 0)} · "
            f"LOW {counts.get('LOW', 0)} · review {counts.get('NEEDS_REVIEW', 0)}"
        )
    if c3.button(
        "Delete", key=f"del-{r['contract_id']}", help="Deletes the report and the uploaded file"
    ):
        api_client.delete(r["contract_id"])
        st.rerun()
