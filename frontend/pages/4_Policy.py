"""Policy Editor (HLD 11.4): rules as an editable table plus a raw-JSON tab."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from frontend import api_client, ui

ui.page("Policy Editor", "⚙️")
try:
    policies = api_client.policies()
except api_client.APIError as exc:
    ui.show_error(exc)
    st.stop()
pid = st.selectbox("Policy", [p["policy_id"] for p in policies])
policy = api_client.policy(pid)
st.caption(
    f"{policy['name']} · version {policy['version']}. Saving validates the policy and "
    "bumps the patch version; the previous version is kept in history."
)

EDITABLE = [
    "id",
    "name",
    "category",
    "check",
    "fact",
    "expected",
    "threshold",
    "allowed",
    "required_clause",
    "severity",
    "applies_to",
    "policy_text",
    "recommendation_template",
]


def to_frame(p: dict) -> pd.DataFrame:
    rows = []
    for r in p["rules"]:
        row = {k: r.get(k) for k in EDITABLE}
        row["allowed"] = ", ".join(r.get("allowed") or [])
        row["applies_to"] = ", ".join(r.get("applies_to") or [])
        row["required_clause"] = bool(r.get("required_clause", False))
        rows.append(row)
    return pd.DataFrame(rows, columns=EDITABLE)


def from_frame(df: pd.DataFrame) -> list[dict]:
    rules = []
    for rec in df.to_dict("records"):
        rule = {k: v for k, v in rec.items() if v is not None and v == v and v != ""}  # drop NaN/""
        for key in ("allowed", "applies_to"):
            if key in rule:
                rule[key] = [x.strip() for x in str(rule[key]).split(",") if x.strip()]
        if "threshold" in rule:
            rule["threshold"] = float(rule["threshold"])
        if "expected" in rule and isinstance(rule["expected"], str):
            rule["expected"] = rule["expected"].lower() == "true"
        rules.append(rule)
    return rules


def save(body: dict) -> None:
    try:
        saved = api_client.save_policy(pid, body)
    except api_client.APIError as exc:
        st.error(f"Not saved. {exc.message}")
        return
    st.success(f"Saved as version {saved['version']}.")


table_tab, json_tab = st.tabs(["Rules", "Raw JSON"])
with table_tab:
    edited = st.data_editor(
        to_frame(policy),
        hide_index=True,
        use_container_width=True,
        num_rows="dynamic",
        key=f"rules-{pid}-{policy['version']}",
        column_config={
            "severity": st.column_config.SelectboxColumn(
                "severity", options=["HIGH", "MEDIUM", "LOW"]
            ),
            "check": st.column_config.SelectboxColumn(
                "check",
                options=[
                    "CLAUSE_PRESENT",
                    "BOOLEAN_EQUALS",
                    "NUMERIC_MIN",
                    "NUMERIC_MAX",
                    "ENUM_IN",
                ],
            ),
            "threshold": st.column_config.NumberColumn("threshold"),
            "required_clause": st.column_config.CheckboxColumn("required_clause"),
        },
    )
    if st.button("Save rules", type="primary"):
        save({**policy, "rules": from_frame(edited)})
with json_tab:
    raw = st.text_area(
        "Policy JSON",
        json.dumps(policy, indent=2),
        height=480,
        key=f"raw-{pid}-{policy['version']}",
    )
    if st.button("Save JSON"):
        try:
            body = json.loads(raw)
        except json.JSONDecodeError as exc:
            st.error(f"Not saved. Invalid JSON: {exc}")
        else:
            save(body)
