# 13 Gold set and evaluation

Files: `evaluation/gold/` (contracts, `build_gold.py`, `GUIDELINES.md`, `ADJUDICATION.md`,
`labeller_ai/`), `evaluation/eval_ingestion.py`, `eval_segmentation.py`, `eval_facts.py`,
`eval_policy.py`, `run_e2e_eval.py`, `make_rating_sheet.py`, `label_agreement.py`; results in
`evaluation/results/`.

## What

A synthetic test set of 8 contracts with known answers, and scripts that measure each stage and the
whole system against it (metrics E1 to E8 of the HLD).

## Why

Without measured numbers, any claim about accuracy is a guess. Each phase of the build ended with
an evaluation run against acceptance targets, and the results are committed so they can be checked.

## How

### The gold set

| Contract | Type | Planted issues |
|---|---|---|
| GC01 IT support | Vendor | 7-day convenience notice for the vendor only, uncapped liability, auto-renewal, 15-day payment |
| GC02 Master services | Vendor | fully compliant baseline |
| GC03 Facility management | Vendor | Word auto-numbering, no SLA, no indemnity, English law, 30 business days notice |
| GC04 SaaS | SaaS | auto-renewal, 15-day notice for the provider |
| GC05 Software licence | SaaS | uncapped liability, New York law, no SLA |
| GC06 Mutual NDA | NDA | compliant |
| GC07 One-way NDA | NDA | Roman-numeral ARTICLE headings, auto-renewal, Singapore law |
| GC08 Equipment rental | Other | no confidentiality clause |

Each contract is written once as `contract.yaml`. `build_gold.py` generates a DOCX (python-docx,
with a running header and "Page X of Y" footer), a text PDF (LibreOffice headless), a simulated scan
(200 DPI, slight skew, noise, blur, JPEG quality 60, image-only PDF) and `gold.json` with clause
boundaries, categories, facts and expected rule statuses (D6). All 24 files are reproducible.

**Labelling status.** The labels were drafted automatically from the YAML sources (labeller 0). A
second AI labelling from the PDFs only (`labeller_ai/`, D51) agreed on 100% of rule statuses and
97.2% of clause categories; its 8 disagreements are listed in `ADJUDICATION.md` for the owner to
decide. Neither is a human labelling, so the gold labels remain a draft.

### Results

| Metric | What | Target | Result |
|---|---|---|---|
| E1 | Clause classification, test split | macro-F1 at least 0.75 | 0.854 |
| E2 | Segmentation boundaries | F1 at least 0.85 | 1.000 DOCX, 0.986 PDFs |
| E3 | OCR | CER under 5%; text vs scan status agreement at least 90% | CER 1.10%; agreement 100% |
| E4 | Facts and metadata (gold categories) | at least 85% | 100% |
| E5 | Policy violations, end to end | recall at least 85%, precision at least 80% | 88.9% / 100% |
| E6 | Semantic search | precision at 3 at least 70% | 35.2% (recall at 3: 96.5%, MRR 0.909) |
| E7 | LLM explanations | rating at least 4/5, no invented values | 18/20 grounded, 0 invented numbers; AI rating 4.0, human rating pending |
| E8 | Speed | under 30 s for a 20-page text PDF | 0.2 to 0.3 s per text contract, about 7 s per scanned one |

**About E6.** Most rules have exactly one correct clause, so precision at 3 cannot exceed about 33%
for those rules even with a perfect ranking. Recall at 3 (96.5%) and MRR (0.909: the right clause
is almost always ranked first) show the search works; the target is the wrong measure for this
data (recommended change, not yet made).

**Why the numbers are optimistic.** The labels are drafts, the patterns were developed while
looking at these contracts, the scans are simulated, and 8 contracts is a small sample. A
trustworthy estimate needs human labels and contracts never seen during development.

### Scripts

| Script | Measures |
|---|---|
| `eval_ingestion.py` | every file loads; OCR character error rate (Levenshtein) |
| `eval_segmentation.py` | boundary P/R/F1 with fuzzy matching of each clause's first eight words |
| `eval_facts.py` | exact match of the 7 facts and the metadata |
| `eval_policy.py` | status confusion matrix; violation precision and recall |
| `run_e2e_eval.py` | full pipeline, LLM off: E3, E5, E6, E8 |
| `make_rating_sheet.py` | runs with the LLM; writes a rating sheet for two raters and automatic checks (E7) |
| `label_agreement.py` | agreement and Cohen's kappa between two labellings |

## Interview notes

- *Precision vs recall here?* Recall of violations matters more (a missed uncapped liability is
  worse than a false alarm), so its target is higher; precision still matters for trust.
- *What is Cohen's kappa?* Agreement corrected for chance: (observed − expected) / (1 − expected).
- *Why simulate scans?* Reproducible and fast; the downside is optimism, so at least one real scan
  is recommended.
- *What would you do next?* Two human labellers with adjudication, real contracts (CUAD public
  contracts, anonymised Indian ones with permission), at least one real scan, and confidence
  intervals on every metric.
