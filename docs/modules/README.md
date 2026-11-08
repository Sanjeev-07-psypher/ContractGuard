# Module guide

One guide per part of the code. Each guide answers the same questions in the same order:

1. **What** the module does, in one paragraph.
2. **Why** it exists and why it is built this way.
3. **How** it works, step by step.
4. **Callers and dependencies**: who calls it and what it calls.
5. **Data in and out**: the exact types that cross its boundary.
6. **Errors and edge cases**: what can go wrong and what happens then.
7. **Configuration**: the settings and pattern files that change its behaviour.
8. **Alternatives considered**: what else was possible and why it was not chosen.
9. **Interview notes**: questions an examiner is likely to ask, with short answers.

Decision numbers such as D23 refer to [`docs/DECISIONS.md`](../DECISIONS.md). HLD section numbers
refer to the high-level design document the project was built from.

| # | Guide | Code |
|---|---|---|
| 01 | [Foundations: models, configuration, errors](01_foundations.md) | `contractguard/models.py`, `config.py`, `errors.py` |
| 02 | [Ingestion and OCR](02_ingestion.md) | `contractguard/ingestion/` |
| 03 | [Cleaning and normalisation](03_preprocessing.md) | `contractguard/preprocessing/` |
| 04 | [Clause segmentation](04_segmentation.md) | `contractguard/segmentation/` |
| 05 | [Clause classification and embeddings](05_classification.md) | `contractguard/classification/`, `contractguard/embeddings/` |
| 06 | [Fact and metadata extraction](06_extraction.md) | `contractguard/extraction/`, `classification/contract_type.py` |
| 07 | [Policy engine](07_policy.md) | `contractguard/policy/`, `policies/` |
| 08 | [LLM explanations](08_llm.md) | `contractguard/llm/` |
| 09 | [Pipeline, report and CLI](09_pipeline.md) | `contractguard/pipeline.py`, `report/`, `cli.py` |
| 10 | [Backend API](10_backend.md) | `backend/` |
| 11 | [Streamlit UI](11_frontend.md) | `frontend/` |
| 12 | [Training the classifier](12_training.md) | `training/` |
| 13 | [Gold set and evaluation](13_evaluation.md) | `evaluation/` |
| 14 | [Tests and tooling](14_testing.md) | `tests/`, `pyproject.toml` |

## The pipeline in one picture

```
file ──► ingestion ──► cleaning ──► segmentation ──► classification ──► metadata + facts
 (PDF/DOCX)  Document     CleanedText    list[Clause]     Clause.categories    ContractMeta, Fact

         ──► policy engine ──► explainer ──► report builder ──► Report (JSON)
               list[Finding]     Finding.explanation
```

Every arrow carries a Pydantic model from `contractguard/models.py`, never a loose dictionary.
The policy engine decides every status and the policy file decides every severity. The LLM only
writes explanations after that, and its answers are checked before they are shown.
