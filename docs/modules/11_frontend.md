# 11 Streamlit UI

Files: `frontend/app.py`, `home.py`, `ui.py`, `api_client.py`, `frontend/pages/1_Upload.py`,
`2_Report.py`, `3_Clauses.py`, `4_Policy.py`.

## What

A web interface with five pages: Home, Upload & Analyze, Report Dashboard, Clause Explorer and
Policy Editor. It talks to the backend over HTTP only and never imports the NLP code.

## Why

Reviewers are not programmers. Streamlit gives a working, accessible interface in pure Python,
which the HLD fixed as the UI technology for this project.

## How

- **`app.py`** defines the navigation with `st.navigation`, so the sidebar shows readable names and
  short URLs (`/upload`, `/report`, `/clauses`, `/policy`) instead of file names (D46).
- **`api_client.py`** wraps `requests`: every call turns HTTP errors into an `APIError` with the
  backend's `error_code` and message, and a connection failure into "Cannot reach the backend at
  ...". The backend URL comes from `CG_API_URL` or `frontend.api_url`.
- **`ui.py`** holds shared pieces: page setup, the disclaimer banner on every page, status and
  severity badges, the contract picker, and evidence highlighting.

| Page | What the reviewer does |
|---|---|
| Home | Reads what the tool does; sees whether the backend, models, embeddings, OCR and LLM are ready |
| Upload & Analyze | Chooses a file, contract type (or auto), organisation name, policy and the AI toggle; watches a progress bar with the current stage; sees recent analyses |
| Report Dashboard | Overview card (title, type, dates, governing law, parties and roles, OCR pages), counts, executive summary, warnings, clause checklist, JSON download, and findings filtered by status, severity and category; each finding expands to show expected and found, location, the evidence with the quoted sentence highlighted, and the explanation |
| Clause Explorer | Filters by clause kind; a table of clauses with categories, confidence, how each was classified and the location; selecting a row shows the full text and every category score |
| Policy Editor | Picks a policy; edits rules in a table or as raw JSON; saving validates against the schema and creates a new version |

**Accessibility.** Status and severity badges always carry text, never colour alone (WCAG 1.4.1),
and dark mode is styled.

## Callers and dependencies

Run with `streamlit run frontend/app.py`. Depends on Streamlit, pandas and requests; reads only the
settings from `contractguard.config`.

## Data in and out

In: user actions. Out: HTTP calls to the backend; the report JSON is shown and offered for download.

## Errors and edge cases

- Backend down: a clear message instead of a stack trace.
- Models not loaded: the home page shows the backend's reason and uploads are refused with it.
- Upload progress polls `/status` every `frontend.poll_seconds` (2 s) until DONE or FAILED.

## Alternatives considered

- **React or Vue front end**: more control, but a second language and build toolchain for a
  single-developer project.
- **Gradio**: suited to single-function demos, weaker for multi-page dashboards and tables.

## Interview notes

- *Why does the UI not import `contractguard` directly?* Separation: the UI could be replaced
  without touching the NLP, and the same API serves other clients.
- *How was the UI tested?* Every page runs headless with Streamlit's `AppTest` against a real
  Uvicorn backend in a thread (fake classifier, mock LLM), plus Playwright screenshots at desktop
  and phone widths checked by eye (D47).
- *How do reviewers trust a flag?* Every finding shows the exact clause sentence it is based on,
  with the location, and the explanation's quote is checked to be in that clause.
