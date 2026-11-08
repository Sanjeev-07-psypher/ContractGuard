# 08 LLM explanations

Files: `contractguard/llm/base.py`, `gemini.py`, `ollama.py`, `mock.py`, `prompts.py`,
`explainer.py`; wording for templates in `config/templates.yaml`.

## What

Adds a plain-English `Explanation` to every flagged finding (NON_COMPLIANT, MISSING,
NEEDS_REVIEW) and writes a short executive summary. Each explanation has a one-sentence summary,
2 to 4 sentences of explanation, why it matters, a suggested review action, and a quote from the
clause.

## Why

A finding such as "R03 NON_COMPLIANT, found 7 days" is precise but terse. Reviewers, especially
non-lawyers in procurement, understand faster with a short explanation tied to the clause. LLMs
write that well. They can also invent things, so the design gives them **no power over results**
and **checks every answer** before showing it.

## How

### Providers (`base.py`, `gemini.py`, `ollama.py`, `mock.py`)

All implement one interface, `generate_json(system, user, schema, temperature, timeout_s)`, and
raise `LLMError(retryable=...)` on failure:

- **Gemini** through the `google-genai` SDK with JSON output constrained by a response schema.
  HTTP 408, 429 and 5xx are retryable.
- **Ollama** through its local HTTP API (`POST /api/chat` with the JSON schema as `format`), using
  only the standard library. Nothing leaves the machine.
- **Mock** builds a grounded answer from the prompt itself, or replays scripted answers and
  exceptions; used by tests and offline demos.

`make_provider(settings)` returns `None` (templates only) when the provider is `none`, the model
name is missing, or the Gemini key is missing.

### Prompts (`prompts.py`)

The system prompt says: do not give legal advice, do not change status or severity, use only the
clause and policy given, return only JSON. The user prompt carries the contract type, the party
aliases, the rule and policy text, the automated result (status, severity, expected, found,
location) and the clause text. The version string `explain-v1` is part of the cache key, so any
wording change must bump it.

### The explainer (`explainer.py`)

For each flagged finding, the top `llm.max_findings` (15) by severity go to the LLM; the rest get
template explanations.

1. **Cache.** Key = SHA-256 of prompt version, rule, status, clause text, expected, found and model.
   A hit skips the call. The cache is the `llm_cache` SQLite table.
2. **Pacing.** A token-bucket `RateLimiter` allows at most `llm.rpm` (8) calls per minute, to stay
   inside free-tier limits.
3. **Retries.** Retryable errors back off 2 s, 4 s, 8 s (`llm.max_retries` = 3).
4. **Grounding checks** on the answer:
   - `quoted_evidence` must be an exact substring of the clause after whitespace normalisation, and
     empty for MISSING findings (there is no clause to quote);
   - every number in the prose fields must appear somewhere in the prompt (D37), so an invented
     "45 days" cannot reach the reviewer.
5. **One retry** with a correction note if a check fails; after that, the **template
   explanation** is used. The template is built from the finding's own reason, the policy text and
   the rule's recommendation, so it is always correct, just less fluent.
6. **Executive summary.** One call listing the flagged findings; its numbers are checked too. On
   failure, a template summary counts the results and names the top three issues.

Status, severity, reason, expected and found are never changed by this stage.

## Callers and dependencies

`pipeline.run` creates an `Explainer` after the policy engine. If the whole stage raises, the
pipeline retries with templates only and adds a warning: a report is never lost over explanations.

## Data in and out

In: findings, rules, clauses, metadata. Out: the same findings with `explanation` filled, and the
summary text. `Report.llm_used` says whether any explanation came from the LLM.

## Errors and edge cases

| Situation | Result |
|---|---|
| No key, no model, provider `none` | templates, warning "AI explanations are off" |
| Rate limit or timeout | backoff and retry, then template for that finding |
| Answer quotes text not in the clause | one retry, then template |
| Answer contains a number not in the input | one retry, then template |
| LLM returns invalid JSON | counted as an error, then template |

## Configuration

`llm.provider` (`gemini`, `ollama`, `mock`, `none`), `llm.model`, `llm.ollama_host`, `llm.rpm`,
`llm.max_findings`, `llm.temperature` (0.2), `llm.timeout_s`, `llm.max_retries`; environment
variables `LLM_PROVIDER`, `LLM_MODEL`, `GEMINI_API_KEY`.

## Alternatives considered

- **One call for the whole report**: sends much more of the contract, harder to ground, and fails
  all at once.
- **Free-text answers**: harder to check; a JSON schema makes each field testable.
- **Let the LLM decide compliance**: rejected; see the policy engine guide.
- **Retrieval-augmented chat over the contract**: out of scope for V1; the "retrieval" here is the
  exact evidence clause chosen by the deterministic pipeline.

## Interview notes

- *What did you measure (E7)?* With a local Qwen 2.5 3B model through Ollama: 18 of 20 flagged
  findings got an LLM explanation that passed the checks (90%), 2 fell back to templates, and no
  invented numbers reached the report. An AI rating gave 4.0 out of 5 for faithfulness; human
  ratings are still to be collected, so that score is provisional.
- *How do you stop hallucinations?* Narrow input (one clause), JSON schema, an exact-substring check
  on the quote, a check that every number exists in the input, one retry, then a template.
- *Privacy?* With Gemini, only the single clause for a finding is sent. With Ollama, nothing leaves
  the machine. Free-tier Gemini data may be used by Google, so demos use synthetic contracts.
- *Why temperature 0.2?* Low randomness keeps answers close to the input and repeatable, while
  still reading naturally.
