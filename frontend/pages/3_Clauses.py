"""Clause Explorer (HLD 11.3)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from frontend import api_client, ui

ui.page("Clause Explorer", "🔎")
cid = ui.pick_contract()
if cid is None:
    st.stop()
try:
    clauses = api_client.clauses(cid)
except api_client.APIError as exc:
    ui.show_error(exc)
    st.stop()


def location(c: dict) -> str:
    if c.get("page_start"):
        same = c["page_start"] == c.get("page_end")
        return f"Page {c['page_start']}" if same else f"Pages {c['page_start']}-{c['page_end']}"
    return f"Section {c['section_path']}"


kinds = sorted({c["kind"] for c in clauses})
chosen_kinds = st.multiselect("Clause kinds", kinds, default=kinds)
visible = [c for c in clauses if c["kind"] in chosen_kinds]
table = pd.DataFrame(
    [
        {
            "id": c["clause_id"],
            "number": c.get("number") or "",
            "heading": c.get("heading") or "",
            "kind": c["kind"],
            "categories": ", ".join(c.get("categories") or []),
            "confidence": max((c.get("scores") or {}).values(), default=None),
            "classified by": c.get("classified_by"),
            "low confidence": c.get("low_confidence"),
            "location": location(c),
        }
        for c in visible
    ]
)

event = st.dataframe(
    table,
    hide_index=True,
    use_container_width=True,
    on_select="rerun",
    selection_mode="single-row",
    key="clause_table",
    column_config={
        "confidence": st.column_config.ProgressColumn(
            "confidence", min_value=0.0, max_value=1.0, format="%.2f"
        )
    },
)
rows = event.selection.rows if event and event.selection else []
if not visible:
    st.stop()
selected = visible[rows[0]] if rows else visible[0]
if not rows:
    st.caption("Select a row to see its full text. Showing the first clause.")

st.subheader(f"{selected['clause_id']} · {selected.get('heading') or 'Untitled'}")
st.markdown(
    f"<span class='cg-muted'>{location(selected)} · {selected['kind']} · classified by "
    f"{selected.get('classified_by')}</span>",
    unsafe_allow_html=True,
)
st.markdown(ui.highlight(selected["text"], None), unsafe_allow_html=True)
scores = selected.get("scores") or {}
if scores:
    st.markdown("**Category scores**")
    st.bar_chart(
        pd.DataFrame({"score": scores}).sort_values("score", ascending=False), horizontal=True
    )
else:
    st.caption("This clause kind is not classified.")
