# 07 Policy engine

Files: `contractguard/policy/engine.py`, `schema.py`; `policies/default_vendor_v1.json`,
`policies/policy.schema.json`, `policies/history/`; wording in `config/templates.yaml`.

## What

Checks a contract against an organisation's policy and returns one `Finding` per rule with a
status (`NON_COMPLIANT`, `MISSING`, `NEEDS_REVIEW`, `COMPLIANT`, `NOT_APPLICABLE`), a severity,
what was expected, what was found, where, the evidence and a plain-English reason.

## Why

This is the part that must be trustworthy. It is **deterministic**: the same contract and policy
always give the same findings, every decision can be traced to a clause and a fact, and the
rules are a JSON file a legal team can read and edit. **The LLM is never consulted here** (HLD 0.3).

## How

### The policy file

`default_vendor_v1.json` (version 1.0.0) holds 10 rules:

| Rule | Category | Check | Expectation | Severity | Applies to |
|---|---|---|---|---|---|
| R01 | Liability | BOOLEAN_EQUALS `liability.has_cap` | true | HIGH | Vendor, SaaS |
| R02 | Liability | BOOLEAN_EQUALS `liability.is_uncapped` | false | HIGH | Vendor, SaaS |
| R03 | Termination | NUMERIC_MIN `termination.notice_days` | at least 30 | HIGH | Vendor, SaaS |
| R04 | Termination | BOOLEAN_EQUALS `termination.counterparty_unilateral` | false | MEDIUM | Vendor, SaaS |
| R05 | Renewal | BOOLEAN_EQUALS `renewal.is_automatic` | false | MEDIUM | all types |
| R06 | SLA | CLAUSE_PRESENT | present | MEDIUM | Vendor, SaaS |
| R07 | Confidentiality | CLAUSE_PRESENT | present | HIGH | all types |
| R08 | Governing law | ENUM_IN `governing_law.jurisdiction` | India | MEDIUM | all types |
| R09 | Payment | NUMERIC_MIN `payment.due_days` | at least 30 | LOW | Vendor, SaaS |
| R10 | Indemnification | CLAUSE_PRESENT | present | MEDIUM | Vendor, SaaS |

Each rule also has `policy_text` (the policy in words, also used as the semantic search query) and
`recommendation_template` (the review action shown to the reviewer).

### Evaluating one rule (`PolicyEngine.evaluate_rule`)

1. **Contract type.** Not in `applies_to`: `NOT_APPLICABLE`.
2. **Matching clauses.** `BODY` or `EXHIBIT` clauses whose categories include the rule's category.
3. **None found.** Semantic search: embed `policy_text`, compare with every body clause, and if
   the best cosine similarity reaches `policy.tau_missing` (0.55), return `NEEDS_REVIEW` pointing at
   that clause ("possibly covered by clause 9"). Otherwise `MISSING` if the rule needs the clause
   (CLAUSE_PRESENT or `required_clause`), else `NOT_APPLICABLE`.
4. **Only low-confidence clauses** (from the embedding fallback): `NEEDS_REVIEW`.
5. **CLAUSE_PRESENT**: `COMPLIANT`.
6. **The fact.** Missing, ambiguous or `None`: `NEEDS_REVIEW` ("could not be determined").
7. **Compare** (`compare`): BOOLEAN_EQUALS is an identity test; NUMERIC_MIN is `value >= threshold`,
   NUMERIC_MAX is `value <= threshold`; ENUM_IN checks whether any allowed value appears in the
   value ("India (Karnataka)" contains "India"). Pass: `COMPLIANT`; fail: `NON_COMPLIANT`. A value of
   the wrong type for the check gives `NEEDS_REVIEW`.

**Severity** comes from the rule for NON_COMPLIANT and MISSING, is LOW for NEEDS_REVIEW, and is
empty otherwise. **Location** is "Page N" / "Pages N-M" for PDFs and "Section X" for DOCX.
**Reasons** come from `templates.yaml`, for example "Termination notice is 7 days; the policy
requires at least 30 days." Findings are sorted by status, then severity, then clause position.

### Policy files (`schema.py`)

- `validate_policy` checks a policy against `policy.schema.json` (JSON Schema draft 2020-12) and
  reports every error in one message, plus duplicate rule ids.
- `load_policy` only accepts ids made of letters, digits and underscores (no path tricks).
- `save_policy` (used by `PUT /policies/{id}`) validates the new version, copies the current file to
  `policies/history/{id}@{version}.json`, and bumps the patch version. Every report records the
  policy version it used.

## Callers and dependencies

`pipeline.run` creates `PolicyEngine(policy, embedder, settings)` and calls `evaluate`. The backend
policy endpoints call `list_policies`, `load_policy` and `save_policy`. Uses `jsonschema` and the
embedding service.

## Data in and out

In: contract type, classified clauses, facts. Out: `list[Finding]` without explanations.

## Errors and edge cases

- No embedding model: step 3's search is skipped, so an empty category goes straight to MISSING or
  NOT_APPLICABLE, and the report carries a warning.
- A policy file that fails the schema: `POLICY_INVALID`, and the edit is not saved.

## Configuration

`policy.default_policy_id`, `policy.tau_missing` (a policy file can override it in
`thresholds.tau_missing`), `policy.policies_dir`.

## Alternatives considered

- **Ask the LLM whether a clause complies**: not reproducible, not auditable, and can be wrong
  with confidence. Rejected by design.
- **A rules engine library (Drools, durable-rules)**: more power than 5 check types need, and a
  harder file format for legal teams.
- **Hard-coded rules in Python**: a policy change would need a code change and a release.

## Interview notes

- *Measured result (E5)?* End to end with the trained classifier: violation recall 88.9% (16 of 18
  violations found) and precision 100% on all three formats; exact status accuracy 93.8%. The misses
  are GC03's missing SLA and indemnity clauses, reported as NEEDS_REVIEW (semantic search found a
  similar clause) instead of MISSING: cautious, not silent.
- *What counts as a violation?* NON_COMPLIANT or MISSING.
- *Why NEEDS_REVIEW instead of a guess?* A wrong COMPLIANT hides risk and a wrong NON_COMPLIANT
  wastes time and trust. "Please look" is the honest answer when the evidence is unclear.
- *How do you prevent a policy edit from breaking the system?* Schema validation before saving,
  versioned history, and the version recorded in every report.
