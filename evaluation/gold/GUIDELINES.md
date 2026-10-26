# Gold set labelling guideline

The gold set is ContractGuard's ground truth for evaluation (HLD §12.2). It is **never** used for
training or threshold tuning. These rules make two labellers' work comparable.

## Status of the current labels

| Labeller | Who | Status |
|---|---|---|
| 0 (draft) | Automated draft generated from the YAML sources | Done for GC01–GC08 |
| 1 | Sanjeev | To do |
| 2 | Second team member | To do |
| AI check | AI assistant, from `contract_text.pdf` only (`labeller_ai/`) | Done 2026-10-26; **not** a human labeller, does not replace 1 or 2 |

Labellers 1 and 2 work **independently** from the generated files (`contract.docx` or
`contract_text.pdf`), without looking at `gold.json` or the YAML `gold:` block. Use the blank sheet
`labelling_sheet.csv` (one copy per labeller per contract). Disagreements with each other or with
the draft are resolved in a short meeting and logged in `ADJUDICATION.md`.

## 1. Clause boundaries

- A **clause** is a numbered section (`7`) or sub-section (`7.2`), or an `ARTICLE` heading, with its
  heading and body.
- Lettered and roman sub-items `(a)`, `(i)` belong to their parent clause.
- A numbered heading with **no body of its own** (for example `12. TERMINATION` followed directly by
  `12.1 …`) is not a separate clause. Its heading line is part of the first sub-clause.
- Text before the first numbered clause is the `PREAMBLE`. The block starting `IN WITNESS WHEREOF`
  is `SIGNATURE`. Headings beginning `Schedule`, `Exhibit`, `Annex`, `Appendix` start an `EXHIBIT`.
- A clause whose heading is `Definitions` or `Interpretation` (plural, or `Definitions and
  Interpretation`) is `DEFINITIONS`. `Definition of Confidential Information` is a normal `BODY`
  clause.
- Record each boundary as the clause number (or `PREAMBLE`, `SIGNATURE`, the exhibit heading) plus
  its first 8 words, with dashes and curly quotes written as `-` and `"`.

## 2. Categories (multi-label)

Give a `BODY` or `EXHIBIT` clause **every** category whose subject it substantially deals with;
otherwise `OTHER`. `PREAMBLE`, `SIGNATURE` and `DEFINITIONS` get no category.

| Category | Label it when the clause… | Do not label |
|---|---|---|
| CONFIDENTIALITY | imposes duties to keep information secret, defines confidential information, or governs its return | a passing mention ("Customer Data is confidential") inside another topic is still enough only if a duty is stated |
| TERMINATION | gives a right to end the contract (convenience, breach, insolvency) or sets what happens on termination | survival sentences alone |
| PAYMENT | sets fees, invoicing, payment period, taxes, interest | security deposits only if refund timing is the subject (still PAYMENT) |
| LIABILITY | limits, excludes or extends a party's liability for losses | indemnities (use INDEMNIFICATION) |
| INDEMNIFICATION | obliges a party to indemnify, defend or hold harmless | general liability limits |
| IP | allocates ownership of intellectual property or states that no licence is granted | a plain right-to-use grant with no ownership terms (OTHER) |
| GOVERNING_LAW | chooses the governing law (jurisdiction of courts may sit in the same clause) | an arbitration-only clause (OTHER) |
| RENEWAL | says whether and how the term renews or is extended | an initial term with no renewal content (OTHER) |
| SLA | sets measurable service levels: availability, response or resolution times, service credits | maintenance duties without measurable targets |
| OTHER | anything else | |

## 3. Facts

Record the value a careful reviewer would extract, using these conventions:

| Fact | Value | Conventions |
|---|---|---|
| `termination.notice_days` | integer days | Prefer the termination-for-convenience notice. If several parties have one, take the minimum. Weeks ×7, months ×30, years ×365, business days → ceil(n × 7/5). Breach-cure periods do not count. `null` if no convenience or notice-based termination right exists |
| `termination.counterparty_unilateral` | true / false / null | true only if the convenience right belongs to the counterparty alone |
| `liability.has_cap` | true / false / null | true if any aggregate cap or limit on liability exists, including a formula ("fees paid in the prior 12 months"). `null` if no liability clause |
| `liability.is_uncapped` | true / false / null | true if a party accepts liability for "any and all" losses or unlimited liability **and** no cap exists. A negated sentence ("shall not be liable for any and all damages") does not count |
| `renewal.is_automatic` | true / false / null | `null` if the contract says nothing about renewal |
| `payment.due_days` | integer days | the period to pay an invoice; "Net 30" = 30 |
| `governing_law.jurisdiction` | normalized text | use the alias table in `config/patterns.yaml` (`India`, `UK (England and Wales)`, `USA (New York)`, `Singapore`) |

**Dates** (`meta`): write ISO dates. The expiry date follows the legal reading: a term of N years
from 1 April 2026 ends on 31 March of year 2026+N (decision D9). If the term starts on an
event with no fixed date (for example delivery), write `null`.

## 4. Expected rule statuses

For every rule R01–R10 in `policies/default_vendor_v1.json`, record the status an expert reviewer
would assign, and the clause numbers that are the evidence:

1. The rule's `applies_to` does not include the contract type → `NOT_APPLICABLE`.
2. No clause of the rule's category exists → `MISSING` if the rule is `CLAUSE_PRESENT` or has
   `required_clause: true`, otherwise `NOT_APPLICABLE`. Cite no clauses.
3. The clause exists but the value cannot be determined → `NEEDS_REVIEW`.
4. Otherwise compare the fact with the rule → `COMPLIANT` or `NON_COMPLIANT`.

Label what the contract says, not what the system is expected to output. If you believe the system
will get a case wrong, label it correctly anyway; that is what the evaluation measures.

## 5. Agreement

Report per contract: boundary agreement (exact number match), category agreement (Cohen's kappa
per category over clauses), fact agreement (exact match) and rule-status agreement (exact match).
Log every disagreement and its resolution in `ADJUDICATION.md`.
