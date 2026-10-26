"""Report Dashboard (HLD 11.2)."""

from __future__ import annotations

import json

import streamlit as st

from frontend import api_client, ui

ui.page("Report Dashboard", "📊")
cid = ui.pick_contract()
if cid is None:
    st.stop()
try:
    report = api_client.report(cid)
except api_client.APIError as exc:
    ui.show_error(exc)
    st.stop()

meta, counts = report["meta"], report["counts"]
by_clause = {c["clause_id"]: c for c in report["clauses"]}

# --- overview ---------------------------------------------------------------------------------
with st.container(border=True):
    st.subheader(meta.get("title") or report["filename"])
    o1, o2, o3 = st.columns(3)
    o1.markdown(
        f"**Type:** {ui.CONTRACT_TYPES.get(meta['contract_type'], meta['contract_type'])}"
        f" ({'selected' if meta['contract_type_source'] == 'user' else 'detected'})"
    )
    o1.markdown(f"**File:** {report['filename']} ({(report.get('file_type') or '').upper()})")
    o2.markdown(f"**Effective:** {meta.get('effective_date') or 'not found'}")
    o2.markdown(f"**Expiry:** {meta.get('expiry_date') or 'not found'}")
    o3.markdown(f"**Governing law:** {meta.get('governing_law') or 'not found'}")
    ocr = report.get("ocr_pages") or []
    o3.markdown(f"**OCR pages:** {', '.join(map(str, ocr)) if ocr else 'none'}")
    roles = {
        "OUR_ORG": "our organization",
        "COUNTERPARTY": "counterparty",
        "UNKNOWN": "role unknown",
    }
    for p in meta.get("parties", []):
        st.markdown(f"- {p['name']} ({p.get('alias') or 'no alias'}): {roles[p['role']]}")

# --- KPI tiles --------------------------------------------------------------------------------
tiles = [
    ("Clauses", "CLAUSES"),
    ("High", "HIGH"),
    ("Medium", "MEDIUM"),
    ("Low", "LOW"),
    ("Missing", "MISSING"),
    ("Needs review", "NEEDS_REVIEW"),
    ("Compliant", "COMPLIANT"),
]
for col, (label, key) in zip(st.columns(len(tiles)), tiles, strict=True):
    col.metric(label, counts.get(key, 0))

if report.get("executive_summary"):
    st.info(report["executive_summary"])

for w in report.get("warnings", []):
    st.warning(w)

left, right = st.columns([1, 3])
with left:
    st.subheader("Clause checklist")
    for cat, present in report["clause_checklist"].items():
        st.markdown(
            f"{'✅' if present else '❌'} {ui.CATEGORY_LABELS.get(cat, cat)}"
            f" <span class='cg-muted'>({'found' if present else 'not found'})</span>",
            unsafe_allow_html=True,
        )
    st.download_button(
        "Download report (JSON)",
        json.dumps(report, indent=2),
        file_name=f"{report['filename']}.report.json",
        mime="application/json",
        use_container_width=True,
    )

with right:
    st.subheader("Findings")
    findings = report["findings"]
    f1, f2, f3 = st.columns(3)
    statuses = f1.multiselect(
        "Status",
        ui.STATUS_ORDER,
        default=[s for s in ui.STATUS_ORDER if s != "NOT_APPLICABLE"],
        format_func=ui.STATUS_LABELS.__getitem__,
    )
    severities = f2.multiselect(
        "Severity", ["HIGH", "MEDIUM", "LOW", "none"], default=["HIGH", "MEDIUM", "LOW", "none"]
    )
    categories = sorted({f["category"] for f in findings})
    cats = f3.multiselect("Category", categories, default=categories)
    shown = [
        f
        for f in findings
        if f["status"] in statuses
        and f["category"] in cats
        and (f["severity"] or "none") in severities
    ]
    if not shown:
        st.caption("No findings match the filters.")
    for status in ui.STATUS_ORDER:
        group = [f for f in shown if f["status"] == status]
        if not group:
            continue
        st.markdown(f"#### {ui.STATUS_LABELS[status]} ({len(group)})")
        for f in group:
            title = f"{f['rule_id']} · {f['rule_name']} · {f.get('location') or 'no location'}"
            with st.expander(title, expanded=status in ("NON_COMPLIANT", "MISSING")):
                st.markdown(ui.status_badges(f), unsafe_allow_html=True)
                e1, e2 = st.columns(2)
                e1.markdown(f"**Expected:** {f.get('expected') or '-'}")
                e2.markdown(f"**Found:** {f.get('found') or '-'}")
                st.markdown(f"**Why flagged:** {f['reason']}")
                ex = f.get("explanation")
                quote = (ex or {}).get("quoted_evidence") or f.get("evidence_text")
                for clause_id in f.get("clause_ids", []):
                    c = by_clause.get(clause_id)
                    if c:
                        st.markdown(
                            f"<span class='cg-muted'>Clause {c.get('number') or clause_id}"
                            f" · {c['section_path']}</span>",
                            unsafe_allow_html=True,
                        )
                        st.markdown(ui.highlight(c["text"], quote), unsafe_allow_html=True)
                if ex:
                    label = "AI-generated" if ex["source"] == "llm" else "Template"
                    st.markdown(
                        f"**Explanation** <span class='cg-muted'>({label}"
                        f"{', ' + ex['model'] if ex.get('model') else ''})</span>",
                        unsafe_allow_html=True,
                    )
                    st.write(ex["explanation"])
                    st.markdown(f"**Why it matters:** {ex['why_it_matters']}")
                    st.markdown(f"**Suggested review action:** {ex['suggested_review_action']}")

st.caption(
    f"Policy {report['policy_id']} v{report['policy_version']} · pipeline "
    f"{report['pipeline_version']} · generated {report['generated_at'][:19].replace('T', ' ')}"
)
