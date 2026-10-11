import json

import pandas as pd
import streamlit as st

from src.crawler import run_crawl
from src.database import (
    connect,
    dashboard_metrics,
    get_change_history,
    get_scholarship,
    init_db,
    list_scholarships,
)

st.set_page_config(page_title="Scholarship Intelligence", page_icon="🎓", layout="wide")
init_db()

st.title("🎓 Scholarship Intelligence Crawler")
st.caption("Discover, extract, assess source credibility, store and monitor scholarship opportunities.")
st.info(
    "Search results and third-party pages are discovery hints only. A record is marked VERIFIED only "
    "when its source is recognized as official and its evidence-based score reaches 95%."
)

with st.sidebar:
    st.header("Crawler controls")
    max_pages = st.slider("Maximum candidate pages per run", min_value=5, max_value=150, value=40, step=5)
    if st.button("Run crawler now", type="primary", use_container_width=True):
        with st.spinner("Discovering and checking source pages. This can take several minutes..."):
            try:
                result = run_crawl(max_pages=max_pages)
                st.success(f"Crawl run {result['run_id']} finished")
                st.json(result)
                st.rerun()
            except Exception as exc:
                st.error(f"Crawler failed: {exc}")
    st.markdown("---")
    st.markdown("**Run repeatedly from a terminal:**")
    st.code("python -m src.crawler --loop-hours 24", language="bash")
    st.caption("Repeated runs revisit previously stored source URLs to detect updates or verification failures.")

metrics = dashboard_metrics()
cols = st.columns(7)
metric_items = [
    ("Total records", metrics["total"]),
    ("Verified", metrics["verified"]),
    ("Review required", metrics["review_required"]),
    ("Active / expiring", metrics["active"]),
    ("Expired", metrics["expired"]),
    ("Stale / unverified", metrics["stale"]),
    ("Average confidence", f"{metrics['average_confidence']}%"),
]
for col, (label, value) in zip(cols, metric_items):
    col.metric(label, value)
st.caption(f"Records updated in the last 7 days: {metrics['recently_updated']}")

st.subheader("Scholarship records")
search_col, status_col = st.columns([2, 1])
search_text = search_col.text_input("Search by scholarship, provider, eligibility or source URL")
status_options = [
    "All", "ACTIVE", "EXPIRING_SOON", "EXPIRED", "REVIEW_REQUIRED", "NO_LONGER_VERIFIABLE"
]
status_filter = status_col.selectbox("Current status", status_options)
rows = list_scholarships(search_text=search_text, status=status_filter, limit=1000)

if not rows:
    st.warning(
        "No records found. Run the crawler and inspect Recent crawl errors if discovery or source websites fail. "
        "An empty result does not mean there are no scholarships; some websites block automated requests."
    )
else:
    table = pd.DataFrame([
        {
            "ID": row["id"],
            "Scholarship": row["name"],
            "Provider": row["provider"],
            "Source type": row["source_type"],
            "Benefit": row["amount_benefit"],
            "Deadline": row["closing_date"],
            "Current status": row["current_status"],
            "Verification": row["verification_status"],
            "Confidence": f"{row['confidence_score']:.1f}%",
            "Last seen": row["last_seen_at"],
        }
        for row in rows
    ])
    st.dataframe(table, use_container_width=True, hide_index=True)

    selected_id = st.selectbox(
        "Open scholarship details",
        [row["id"] for row in rows],
        format_func=lambda value: next(
            (f"{row['name']} (ID {row['id']})" for row in rows if row["id"] == value), str(value)
        ),
    )
    record = get_scholarship(selected_id)
    if record:
        st.markdown("---")
        st.subheader(record["name"])
        left, right = st.columns(2)
        with left:
            st.write("**Provider:**", record["provider"])
            st.write("**Benefit:**", record["amount_benefit"])
            st.write("**Eligibility:**", record["eligibility"])
            st.write("**Academic requirements:**", record["academic_requirements"])
            st.write("**Education level:**", record["education_level"])
            st.write("**Income criteria:**", record["income_criteria"])
            st.write("**Age criteria:**", record["age_criteria"])
            st.write("**Gender criteria:**", record["gender_criteria"])
            st.write("**Category criteria:**", record["category_criteria"])
            st.write("**Domicile criteria:**", record["domicile_criteria"])
            st.write("**Institution criteria:**", record["institution_criteria"])
            st.write("**Documents:**", record["documents_required"])
            st.write("**Selection:**", record["selection_process"])
            st.write("**Renewal:**", record["renewal_requirements"])
        with right:
            st.write("**Current status:**", record["current_status"])
            st.write("**Verification:**", record["verification_status"])
            st.write("**Confidence:**", f"{record['confidence_score']:.1f}%")
            st.write("**Source type:**", record["source_type"])
            st.write("**Official source confirmed:**", "Yes" if record["source_is_official"] else "No — review required")
            st.write("**Opening date:**", record["opening_date"])
            st.write("**Closing date:**", record["closing_date"])
            st.write("**First seen:**", record["first_seen_at"] or "Not available")
            st.write("**Last seen:**", record["last_seen_at"] or "Not available")
            st.write("**Last verified:**", record["last_verified_at"] or "Not verified yet")
            if record["source_is_official"] and record["official_source_url"]:
                st.markdown(f"**Official source:** [{record['official_source_url']}]({record['official_source_url']})")
            else:
                st.write("**Official source:** Not confirmed; check the page URL below")
            if record["source_url"]:
                st.markdown(f"**Page checked:** [{record['source_url']}]({record['source_url']})")
            if record["application_url"]:
                st.markdown(f"**Application link:** [{record['application_url']}]({record['application_url']})")

        with st.expander("Why this confidence score?"):
            try:
                reasons = json.loads(record["confidence_reasons"] or "[]")
            except (TypeError, json.JSONDecodeError):
                reasons = []
            for reason in reasons:
                st.write("•", reason)
            if not reasons:
                st.write("No score explanation was saved for this record.")

        with st.expander("Source evidence"):
            try:
                evidence = json.loads(record["evidence_json"] or "{}")
            except (TypeError, json.JSONDecodeError):
                evidence = {}
            if evidence:
                st.json(evidence)
            else:
                st.write("No field-level evidence was retained.")

        with st.expander("Change history"):
            changes = get_change_history(selected_id)
            if changes:
                st.dataframe(pd.DataFrame(changes), use_container_width=True, hide_index=True)
            else:
                st.write("No changes detected for this record yet.")

with st.expander("Recent crawl runs and errors"):
    with connect() as conn:
        runs = pd.read_sql_query("SELECT * FROM crawl_runs ORDER BY id DESC LIMIT 20", conn)
        errors = pd.read_sql_query("SELECT * FROM crawl_errors ORDER BY id DESC LIMIT 30", conn)
    st.markdown("**Recent crawl runs**")
    st.dataframe(runs, use_container_width=True, hide_index=True)
    st.markdown("**Recent crawl errors**")
    if errors.empty:
        st.success("No crawl errors have been recorded yet.")
    else:
        st.dataframe(errors, use_container_width=True, hide_index=True)

st.caption(
    "Confidence is a rule-based evidence score, not a statistical probability. Records marked REVIEW REQUIRED "
    "must be checked against the linked primary source before relying on them."
)
