"""Streamlit demo for the PHI de-identifier.

Usage:
    uv run streamlit run src/phi/app.py
"""

from __future__ import annotations

import streamlit as st

from phi.deidentify import deidentify
from phi.models import DeidConfig

st.set_page_config(page_title="PHI De-identifier", page_icon="🛡️")

st.title("🛡️ PHI De-identifier")
st.caption(
    "Hybrid de-identification demo: rule-based recognizers + spaCy NER + optional LLM. "
    "This is a portfolio demo, not a certified de-identification solution."
)

with st.sidebar:
    st.header("Settings")
    strategy = st.selectbox("Redaction strategy", ["mask", "hash", "surrogate"])
    use_ner = st.toggle("Use NER layer", value=True)
    use_llm = st.toggle("Use LLM second pass", value=False)
    st.markdown("---")
    st.markdown(
        "**Privacy note:** pasted text is processed in-memory. "
        "No data is logged or retained by this demo."
    )

note = st.text_area(
    "Paste a clinical note",
    height=200,
    placeholder="Patient: Jane Smith\nDOB: 01/01/1980\nPhone: 021 123 4567",
)

if st.button("De-identify", type="primary") and note:
    config = DeidConfig(strategy=strategy, use_ner=use_ner, use_llm=use_llm)  # type: ignore[arg-type]
    try:
        result = deidentify(note, config)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    st.subheader("Detected PHI")
    if result.spans:
        rows = []
        for s in result.spans:
            rows.append({"Type": s.type.value, "Text": s.text, "Source": s.source})
        st.dataframe(rows, use_container_width=True)
    else:
        st.info("No PHI detected.")

    st.subheader("Redacted output")
    st.code(result.redacted_text, language=None)

    if result.audit:
        st.subheader("Audit")
        st.json({entry.type.value: entry.count for entry in result.audit})
