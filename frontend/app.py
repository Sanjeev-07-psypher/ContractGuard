"""ContractGuard Streamlit entry point (HLD 11). Run: ``streamlit run frontend/app.py``.

Defines the navigation, so the sidebar shows readable page names.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

navigation = st.navigation(
    [
        st.Page("home.py", title="Home", icon="🛡️", default=True),
        st.Page("pages/1_Upload.py", url_path="upload", title="Upload & Analyze", icon="⬆️"),
        st.Page("pages/2_Report.py", url_path="report", title="Report Dashboard", icon="📊"),
        st.Page("pages/3_Clauses.py", url_path="clauses", title="Clause Explorer", icon="🔎"),
        st.Page("pages/4_Policy.py", url_path="policy", title="Policy Editor", icon="⚙️"),
    ]
)
navigation.run()
