"""Shared Streamlit helpers: page setup, disclaimer, badges, contract picker, evidence highlight."""

from __future__ import annotations

import html
import sys
from pathlib import Path
from typing import Any

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # `streamlit run frontend/app.py` from the repo root
    sys.path.insert(0, str(ROOT))

from frontend import api_client  # noqa: E402

DISCLAIMER = (
    "ContractGuard produces AI-assisted review flags to support contract reviewers. "
    "It is not legal advice and does not determine legal validity."
)
STATUS_LABELS = {
    "NON_COMPLIANT": "Not compliant",
    "MISSING": "Missing",
    "NEEDS_REVIEW": "Needs review",
    "COMPLIANT": "Compliant",
    "NOT_APPLICABLE": "Not applicable",
}
STATUS_ORDER = list(STATUS_LABELS)
# Colour is never the only signal: every badge also carries its text (WCAG 1.4.1).
SEVERITY_STYLE = {
    "HIGH": ("#8a1c1c", "#fde8e8"),
    "MEDIUM": ("#7a4b00", "#fff3d6"),
    "LOW": ("#1f4e79", "#e3eefa"),
    None: ("#2e5e3a", "#e6f4ea"),
}
CATEGORY_LABELS = {
    "CONFIDENTIALITY": "Confidentiality",
    "TERMINATION": "Termination",
    "PAYMENT": "Payment",
    "LIABILITY": "Limitation of liability",
    "INDEMNIFICATION": "Indemnification",
    "IP": "Intellectual property",
    "GOVERNING_LAW": "Governing law",
    "RENEWAL": "Renewal",
    "SLA": "Service levels (SLA)",
    "OTHER": "Other",
}
CONTRACT_TYPES = {
    "auto": "Auto-detect",
    "VENDOR_SERVICE": "Vendor / Service",
    "NDA": "NDA",
    "SAAS_LICENSE": "SaaS / License",
    "OTHER": "Other",
}

CSS = """
<style>
.cg-banner {padding: .6rem .9rem; border-radius: .5rem; background: #f1f3f6; color: #1f2933;
            border-left: 4px solid #52606d; font-size: .9rem; margin-bottom: 1rem;}
.cg-badge {display: inline-block; padding: .1rem .55rem; border-radius: 999px; font-weight: 600;
           font-size: .8rem; margin-right: .35rem; border: 1px solid currentColor;}
.cg-quote {background: #fff8c5; color: #1f2933; padding: 0 .15rem; border-radius: .2rem;}
.cg-clause {white-space: pre-wrap; font-size: .92rem; line-height: 1.5; padding: .6rem .8rem;
            border: 1px solid #d9dee5; border-radius: .5rem; background: #ffffff; color: #1f2933;}
.cg-muted {color: #52606d; font-size: .85rem;}
@media (prefers-color-scheme: dark) {
  .cg-banner {background: #1f2933; color: #e4e7eb; border-left-color: #9aa5b1;}
  .cg-clause {background: #11161c; color: #e4e7eb; border-color: #3e4c59;}
  .cg-muted {color: #9aa5b1;}
}
</style>
"""


def page(title: str, icon: str = "📄") -> None:
    st.set_page_config(page_title=f"{title} · ContractGuard", page_icon=icon, layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    st.markdown(
        f'<div class="cg-banner" role="note">⚠️ {html.escape(DISCLAIMER)}</div>',
        unsafe_allow_html=True,
    )
    st.title(title)


def badge(text: str, severity: str | None) -> str:
    fg, bg = SEVERITY_STYLE.get(severity, SEVERITY_STYLE[None])
    return f'<span class="cg-badge" style="color:{fg};background:{bg}">{html.escape(text)}</span>'


def status_badges(finding: dict[str, Any]) -> str:
    sev = finding.get("severity")
    parts = [badge(STATUS_LABELS.get(finding["status"], finding["status"]), sev)]
    if sev:
        parts.append(badge(f"{sev} severity", sev))
    return "".join(parts)


def highlight(text: str, quote: str | None) -> str:
    """Clause text as safe HTML, with the first occurrence of ``quote`` highlighted."""
    escaped = html.escape(text)
    if quote:
        q = html.escape(quote.strip())
        i = escaped.find(q)
        if i >= 0:
            escaped = f'{escaped[:i]}<mark class="cg-quote">{q}</mark>{escaped[i + len(q) :]}'
    return f'<div class="cg-clause">{escaped}</div>'


def show_error(exc: api_client.APIError) -> None:
    st.error(f"{exc.message}  \n`{exc.error_code}`")


def pick_contract(key: str = "contract_pick") -> str | None:
    """Select a finished analysis; defaults to the one just analysed (session state)."""
    try:
        done = [c for c in api_client.contracts() if c["status"] == "DONE"]
    except api_client.APIError as exc:
        show_error(exc)
        return None
    if not done:
        st.info("No finished analyses yet. Start on the **Upload & Analyze** page.")
        return None
    ids = [c["contract_id"] for c in done]
    current = st.session_state.get("contract_id")
    index = ids.index(current) if current in ids else 0
    labels = {
        c["contract_id"]: f"{c['filename']} · {c['created_at'][:16].replace('T', ' ')}"
        for c in done
    }
    chosen = st.selectbox("Contract", ids, index=index, format_func=labels.__getitem__, key=key)
    st.session_state["contract_id"] = chosen
    return chosen
