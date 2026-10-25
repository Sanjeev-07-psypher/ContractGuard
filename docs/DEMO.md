# Demo script (about 10 minutes)

A walkthrough for presenting ContractGuard. Use only synthetic or public contracts, because
free-tier LLM data may be used by the provider.

## Before the demo

```bash
source .venv/bin/activate
uvicorn backend.main:app --port 8000      # terminal 1
streamlit run frontend/app.py             # terminal 2, opens http://localhost:8501
```

Check the **Home** page: Backend Online, Models Loaded, OCR Available. If you have no API key,
set `LLM_PROVIDER=none` in `.env`: every flag still gets a template explanation.

Files to use: `evaluation/gold/gc01/contract_scanned.pdf` (vendor contract with planted issues,
scanned) and `evaluation/gold/gc02/contract.docx` (a mostly compliant one).

## 1. The problem (1 minute)

"Reviewing vendor contracts against an internal checklist is slow and repetitive. ContractGuard
does the first pass and gives the reviewer a short list of flags, each with the rule, the
evidence and the page. It does not give legal advice; the banner on every page says so."

## 2. Upload a scanned contract (2 minutes)

1. **Upload & Analyze** → choose `gc01/contract_scanned.pdf`, type *Auto-detect*, organization
   *ABC Technologies Pvt. Ltd.*, AI explanations on → **Analyze**.
2. Point at the progress stages: reading with OCR, finding clauses, classifying, checking the
   policy, writing explanations.

## 3. The report (4 minutes)

1. **Overview card**: detected type, both parties and which one is us, effective and expiry
   dates, governing law, OCR pages.
2. **KPI tiles** and the **executive summary**.
3. **Clause checklist**: which of the 9 topics were found.
4. Open **R03 Minimum termination notice**: expected ≥ 30 days, found 7 days, the sentence is
   highlighted inside clause 10, and the explanation is labelled *AI-generated* or *Template*.
   Say: "The rule engine decided this status. The AI only explains it, and its quote is checked
   against the clause text; if it invents a number or misquotes, we fall back to a template."
5. Filter by **Severity = HIGH**; download the JSON report.

## 4. Clause Explorer (1 minute)

Select a clause: full text, its kind, and the category scores as a bar chart. Show a clause
marked *low confidence* if there is one (embedding fallback).

## 5. Change the policy (1 minute)

**Policy Editor** → set R03's threshold to 7 → **Save rules**: version goes 1.0.0 → 1.0.1 and the
old version is kept in `policies/history/`. Re-analyse gc01: R03 is now compliant. Then try an
invalid value (severity `SEVERE` in the JSON tab) to show inline validation. Set it back.

## 6. Honest numbers (1 minute)

Open `evaluation/results/`: classifier macro-F1 (E1), policy recall and precision (E5), OCR error
rate (E3), retrieval (E6), speed (E8). Say what makes them optimistic: synthetic gold contracts,
simulated scans, draft labels, US training data for Indian contracts (README, Known limitations).

## Likely questions

- *What if the LLM is down?* The report is produced anyway with template explanations and a
  warning; status and severity never depend on the LLM.
- *What leaves the machine?* Only the single clause behind each flagged finding, and only when AI
  explanations are on. Ollama keeps everything local.
- *Why not let the LLM decide compliance?* Determinism, auditability, and no hallucinated
  verdicts: the same file and policy always give the same findings.
