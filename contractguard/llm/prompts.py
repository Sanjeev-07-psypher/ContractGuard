"""Versioned prompt templates (HLD 9.4). Changing any text here requires a new PROMPT_VERSION,
because the version is part of the cache key."""

from __future__ import annotations

from typing import Any

PROMPT_VERSION = "explain-v1"

EXPLAIN_SYSTEM = (
    "You help a contract reviewer understand an automated compliance flag.\n"
    "You do not give legal advice. You do not change the status or severity.\n"
    "Use ONLY the clause text and policy provided. If information is missing, say so.\n"
    "Return ONLY valid JSON matching the schema. No markdown."
)

EXPLAIN_USER = '''Contract type: {contract_type}
Our organization is referred to as: {our_alias}; counterparty: {counterparty_alias}
Policy rule: {rule_name} - {policy_text}
Automated result: status={status}, severity={severity}
Expected: {expected} | Found: {found} | Location: {location}
Clause text:
"""{clause_text}"""

Return JSON:
{{"summary": "...one sentence...",
 "explanation": "...2-4 plain-English sentences...",
 "why_it_matters": "...1-2 sentences on business impact...",
 "suggested_review_action": "...what a reviewer should check, phrased as a review step, not legal advice...",
 "quoted_evidence": "...exact sentence copied from the clause text, or empty string if status is MISSING..."}}'''

MISSING_CLAUSE_TEXT = "(No clause covering this rule was found in the contract.)"

GROUNDING_RETRY_NOTE = (
    "\n\nYour previous answer was rejected: quoted_evidence must be copied exactly, character for "
    "character, from the clause text, and every number you mention must appear in the input."
)

EXPLAIN_FIELDS = (
    "summary",
    "explanation",
    "why_it_matters",
    "suggested_review_action",
    "quoted_evidence",
)
EXPLAIN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {k: {"type": "string"} for k in EXPLAIN_FIELDS},
    "required": list(EXPLAIN_FIELDS),
}

SUMMARY_SYSTEM = (
    "You write a short overview of automated contract review flags for a contract reviewer.\n"
    "You do not give legal advice. Use ONLY the findings provided; do not add facts.\n"
    "Return ONLY valid JSON matching the schema. No markdown."
)

SUMMARY_USER = """Contract type: {contract_type}
Counts: {counts}
Findings (status, severity, summary):
{findings}

Return JSON: {{"executive_summary": "...3-5 sentences..."}}"""

SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"executive_summary": {"type": "string"}},
    "required": ["executive_summary"],
}
