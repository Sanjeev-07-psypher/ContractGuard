---
title: ContractGuard
emoji: 🛡️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
short_description: AI-assisted contract review flags against a policy
---

# ContractGuard

Upload a contract (PDF, scanned PDF or DOCX). ContractGuard splits it into clauses, classifies
them, extracts key facts (notice periods, liability caps, renewal, payment terms, governing law),
checks them against a configurable policy and explains every flag with the clause text it is
based on.

**Not legal advice.** ContractGuard produces review flags to support a human reviewer. Use only
synthetic or public contracts in this demo: uploaded files are processed on a shared server, and
with Gemini enabled one clause per flag is sent to Google. Everyone who opens this Space sees
the same list of analysed contracts, and the free hardware has no persistent disk, so uploads and
reports disappear when the Space restarts.

Source code and documentation: see the project's GitHub repository.

## Settings for this Space

| Name | Kind | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | secret (optional) | Turns on AI explanations through Gemini |
| `LLM_MODEL` | variable (optional) | Gemini model name, for example the current Flash model |

Without them, explanations come from templates; every status and severity is decided by the
rules either way.
