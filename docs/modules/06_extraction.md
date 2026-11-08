# 06 Fact and metadata extraction

Files: `contractguard/extraction/sentences.py`, `durations.py`, `dates.py`, `parties.py`,
`entities.py`, `facts.py`, `document.py`, and `contractguard/classification/contract_type.py`;
patterns in `config/patterns.yaml`.

## What

Reads structured values out of the classified clauses:

- **Contract metadata** (`ContractMeta`): title, contract type, the parties with their aliases and
  roles (our organisation or counterparty), effective date, expiry date, term text and governing law.
- **Seven facts** for the policy rules: `termination.notice_days`,
  `termination.counterparty_unilateral`, `liability.has_cap`, `liability.is_uncapped`,
  `renewal.is_automatic`, `payment.due_days`, `governing_law.jurisdiction`.

Every fact carries the clause ids it came from and the **whole sentence** that matched, copied
verbatim from the clause, as evidence.

## Why

Policy rules are about values ("notice of at least 30 days"), not about clause presence alone.
Rules and regular expressions are used instead of a model because there is no labelled data for
these values, the patterns in contracts are formulaic, and every result must be explainable by
pointing at the exact sentence.

## How

### Building blocks

- **`sentences.py`**: spaCy's rule-based sentencizer on each line. Splits after abbreviations
  ("Pvt.", "Ltd.", "No.") or before a lower-case start are merged back. Returns character spans, so
  every sentence is an exact substring of the clause.
- **`durations.py`**: finds durations such as "thirty (30) days", "30 business days", "two months"
  and "Net 45". Digits win over words when both are present. Units convert to days (week 7,
  month 30, year 365); business days become calendar days as ceil(n × 7 / 5), so 30 business days
  is 42 days.
- **`dates.py`**: `dateparser` with day-first order by default (`org.date_order: DMY`, Indian
  convention). Finds the effective date, an explicit expiry date, or a term ("for a period of two
  (2) years from the Effective Date") and computes the end with the **legal reading** (D9): the
  day before the anniversary, so 1 April 2026 for one year ends on 31 March 2027; a 29 February
  start ends on the last day of February.
- **`parties.py`**: a preamble regex finds "between X ... (the "Alias") and Y ... (the "Alias")".
  Each name is cut where its description starts (", a company incorporated ...", "having its office ..."); aliases survive OCR losing the opening quote mark. Roles: a party
  whose name fuzzy-matches our organisation's name (rapidfuzz `token_set_ratio` at least 85) is
  `OUR_ORG`, the other is `COUNTERPARTY`; otherwise aliases decide ("Company", "Client", "Customer", "Licensee", "Buyer" are ours;
  "Vendor", "Supplier", "Provider", "Contractor", "Licensor", "Seller" are theirs).
- **`entities.py`**: when the preamble regex fails, spaCy `en_core_web_sm` ORG entities supply the
  first two organisations as parties.
- **`contract_type.py`**: keyword scores; a hit in the first 3 lines counts 3, a hit in the first
  1,500 characters counts 1; under 2 points means `OTHER`. A type chosen by the user always wins.

### The facts (`facts.py`)

| Fact | Read from | Method |
|---|---|---|
| `termination.notice_days` | TERMINATION clauses | Durations within 12 tokens of "notice" / "prior written" in sentences about terminating. A duration right after "within" is a cure period and is skipped. If some notices are for convenience ("for convenience", "without cause", "at any time"), only those count. Several values: the **minimum**, because the weakest protection is the risk. |
| `termination.counterparty_unilateral` | TERMINATION | True only when every convenience-termination right belongs to the counterparty (its name or alias is the subject); "either party" makes it False. |
| `liability.has_cap`, `liability.is_uncapped` | LIABILITY | Cap phrases ("shall not exceed", "limited to", "maximum aggregate liability") and uncapped phrases ("unlimited liability", "liable for all losses"). A negation cue within 8 tokens before a match cancels it; "including but not limited to" never counts as a cap. |
| `renewal.is_automatic` | RENEWAL | Automatic wording ("shall automatically renew", "evergreen", "unless notice of non-renewal") versus manual ("may be renewed by mutual agreement"). Both found: ambiguous. |
| `payment.due_days` | PAYMENT | In sentences about invoices or payment, the duration right after "within", "net" or "no later than". Different values: ambiguous. |
| `governing_law.jurisdiction` | GOVERNING_LAW | "laws of X", normalised with aliases: "Karnataka" becomes "India (Karnataka)", "England and Wales" becomes "UK (England and Wales)". Different values: ambiguous. |

A fact with no clause of its category has value `None` and no evidence; the policy engine decides
whether that means MISSING or NOT_APPLICABLE. **Ambiguous facts get value `None` and
`ambiguous=True`**, never a guess, and the engine turns them into NEEDS_REVIEW.

### `document.py`

`extract_meta(clauses, our_org, contract_type, date_order)` joins the pieces: the preamble (or the
first characters of the text) for parties and dates, contract type detection on the full text, the
title from the first line, and governing law from the fact extractor.

## Callers and dependencies

`pipeline.run` calls `extract_meta` and then `extract_facts(clauses, meta.parties)`. Uses spaCy,
dateparser and rapidfuzz.

## Data in and out

In: classified `list[Clause]`, our organisation's name, optional user-chosen type, date order.
Out: `ContractMeta` and `dict[str, Fact]` keyed by fact name.

## Errors and edge cases

- Party roles unresolved (our name not found, unusual aliases): a report warning, and
  role-dependent rule R04 may need review.
- Unknown jurisdictions are kept as written and fail the "India only" rule, which is the safe
  direction.
- Known limits: double negation, notice periods stated in a schedule far from the termination
  clause, and amounts of money (no V1 rule uses them, D27).

## Configuration

`patterns.yaml` sections `parties`, `dates`, `durations`, `governing_law`, `facts`, `sentences`;
`contract_types.yaml`; `org.default_name` and `org.date_order` in `settings.yaml`.

## Alternatives considered

- **LLM extraction**: flexible, but values could be invented and results would change between
  runs. The design rule is that the LLM never decides status, so it cannot supply the values the
  status depends on.
- **A trained NER model for durations and money**: no labelled data, and durations are matched
  more precisely by `durations.py` (D27).
- **Effective date plus 365 days for expiry**: off by one day and wrong in leap years (D9).

## Interview notes

- *Measured accuracy (E4)?* 100% of the 7 facts and the metadata on all 3 formats of the 8 gold
  contracts, using gold clause categories. Optimistic: the patterns were written while looking at
  these contracts (D29). End to end, the policy result (E5) is the better measure.
- *How is negation handled?* A window rule similar to NegEx: a cue such as "not", "no", "in no
  event" or "neither" within 8 tokens before the match, in the same sentence, cancels it.
- *Why the minimum notice period?* With 15 days for the vendor and 30 for us, our exposure is the
  15-day exit, so the conservative reading is the minimum, and it is not marked ambiguous.
- *Why whole sentences as evidence?* A reviewer needs the sentence, and because it is a verbatim
  substring, the LLM's quote can be checked against it (D25).
