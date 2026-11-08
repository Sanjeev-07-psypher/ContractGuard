# 01 Foundations: models, configuration, errors

Files: `contractguard/models.py`, `contractguard/config.py`, `contractguard/errors.py`,
`config/*.yaml`, `.env.example`.

## What

Three small modules that every other part of the system imports:

- **`models.py`** defines the Pydantic data models that pass between pipeline stages: `Block`,
  `Document`, `TextSpan`, `CleanedText`, `Clause`, `Party`, `ContractMeta`, `Fact`, `Explanation`,
  `Finding` and `Report`, plus the fixed vocabularies `CATEGORIES` (10 clause categories) and
  `CONTRACT_TYPES` (4 types).
- **`config.py`** loads the runtime settings and the YAML rule files.
- **`errors.py`** defines the exception classes, each with a stable error code.

## Why

- **Typed contracts between stages.** If the segmenter returns a `list[Clause]`, the classifier
  can rely on every clause having `text`, `kind` and `char_start`. A typo in a field name fails at
  once instead of producing a silently empty report. The same models are reused by FastAPI for
  JSON, so the API documentation is generated from them.
- **No magic numbers in code.** Thresholds, regular expressions, label mappings and wording live in
  `config/` so they can be tuned and reviewed without touching Python (HLD 13).
- **Stable error codes.** The UI and API clients react to `error_code` (for example
  `ENCRYPTED_PDF`), while the human-readable `message` can change freely.

## How

### Models

| Model | Produced by | Key fields |
|---|---|---|
| `Block` | ingestion | `text`, `page` (PDF) or `para_index` (DOCX), `is_ocr`, `ocr_confidence`, `style` |
| `Document` | ingestion | `file_type`, `num_pages`, `blocks`, `ocr_pages`, `warnings` |
| `CleanedText` | cleaning | `text`, `spans` (offset map back to blocks and pages), `removed_lines` |
| `Clause` | segmentation, then classification | `clause_id`, `number`, `heading`, `text`, `kind`, `page_start`, `section_path`, `char_start`, `char_end`, `categories`, `scores`, `low_confidence`, `classified_by` |
| `Party`, `ContractMeta` | metadata extraction | parties with alias and role, dates, term, governing law, title, contract type and its source |
| `Fact` | fact extraction | `key`, `value`, `unit`, `clause_ids`, `evidence_text`, `ambiguous`, `note` |
| `Finding` | policy engine | `rule_id`, `status`, `severity`, `expected`, `found`, `location`, `evidence_text`, `reason`, `explanation` |
| `Explanation` | explainer | five text fields, `quoted_evidence`, `source` (`llm` or `template`), `model`, `prompt_version` |
| `Report` | report builder | everything above plus `counts`, `clause_checklist`, `warnings`, versions, `timings_s`, `disclaimer` |

`CleanedText.span_at(offset)` and `pages_for(start, end)` turn a character position back into a
page number. That is how a clause found in the cleaned text knows which PDF page it came from.

### Configuration

`Settings` is a `pydantic-settings` class. Sources, highest priority first:

1. arguments passed to the constructor (used in tests);
2. environment variables with the `CG_` prefix and `__` for nesting, for example
   `CG_LLM__RPM=4` or `CG_OCR__TESSERACT_CMD=...`;
3. the short names from `.env.example`: `LLM_PROVIDER`, `LLM_MODEL`, `GEMINI_API_KEY`;
4. the `.env` file;
5. `config/settings.yaml`.

The API key is a `SecretStr`, so printing the settings shows asterisks. `get_settings()`,
`get_patterns()`, `get_label_map()`, `get_contract_types()` and `get_templates()` are wrapped in
`functools.lru_cache`, so each file is read once; `clear_caches()` resets them for tests.
`Settings.resolve_path()` makes relative paths relative to the repository root, so the program
works from any current directory.

| File | Holds |
|---|---|
| `config/settings.yaml` | limits, OCR, segmentation lengths, model paths, thresholds, LLM pacing, organisation name, date order, disclaimer |
| `config/patterns.yaml` | every regular expression: cleaning, headings, parties, dates, durations, facts, SLA keywords |
| `config/label_map.yaml` | LEDGAR and CUAD label names mapped to ContractGuard categories |
| `config/contract_types.yaml` | keywords and weights for contract type detection |
| `config/templates.yaml` | reason sentences, labels and template explanations |

### Errors

`ContractGuardError(message, code)` is the base class. Subclasses:

- `IngestionError` with codes `UNSUPPORTED_FILE_TYPE`, `FILE_TOO_LARGE`, `TOO_MANY_PAGES`,
  `TOO_MANY_WORDS`, `ENCRYPTED_PDF`, `CORRUPT_FILE`, `OCR_UNAVAILABLE`, `EMPTY_DOCUMENT`;
- `PolicyError` with `POLICY_NOT_FOUND` and `POLICY_INVALID`;
- `ModelArtifactError` when the trained classifier files are missing.

The CLI prints `error [CODE]: message`; the backend stores the message on a failed job or returns
it as `{error_code, message}`.

## Callers and dependencies

Everything imports these modules; they import only Pydantic, pydantic-settings and PyYAML.

## Errors and edge cases

- A missing YAML file raises `FileNotFoundError` at first use. A YAML file that is not a mapping
  raises `ValueError` with the path.
- A wrong setting type (for example `CG_LLM__RPM=abc`) fails validation when settings load, with a
  message naming the field.

## Alternatives considered

- **Plain dictionaries between stages**: shorter to write, but errors surface far from their
  cause. Rejected.
- **dataclasses**: no validation or JSON support. Pydantic gives both, and FastAPI uses it.
- **Settings in Python constants**: rejected by the HLD's rule that thresholds are configuration.

## Interview notes

- *Why Pydantic v2?* Validation from type hints, fast (its core is written in Rust), JSON
  serialisation for the API, and FastAPI uses the same models.
- *How are secrets handled?* Only in `.env` (git-ignored), loaded as `SecretStr`; the `config`
  command prints `gemini_api_key_set: true/false`, never the key.
- *Why `lru_cache` on loaders?* Parsing YAML and compiling regexes once per process keeps every
  stage fast; tests call `clear_caches()` so one test's environment does not leak into another.
- *What is `section_path`?* A location that works without pages, for example `7 > 7.2`. DOCX files
  have no pages, so findings in DOCX contracts are located by section.
