# AI second labelling (check only)

`labels.yaml` is a second labelling of GC01–GC08 made on 2026-10-26 by an AI assistant, at the
project owner's request, following `../GUIDELINES.md`. It was made from `contract_text.pdf` only;
`gold.json` and the YAML `gold:` blocks were not opened until the labels were written.

**These are not independent human labels.** The draft labels (labeller 0) were also produced
automatically, so the two can share the same blind spots and their agreement is likely higher than
two human labellers would reach. Use the result as a consistency check of the draft, not as
inter-annotator agreement in the sense of HLD §12.2. Labellers 1 and 2 are still needed.

Agreement: `python evaluation/label_agreement.py --labeller labeller_ai` writes
`evaluation/results/agreement_labeller_ai.{json,md}`. Every disagreement is logged in
`../ADJUDICATION.md` as pending; none was resolved by the AI.
