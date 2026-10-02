import json
import subprocess
import sys
from pathlib import Path
import pandas as pd
import streamlit as st
from src.database import init_db, list_scholarships, get_scholarship, get_change_history, dashboard_metrics, connect
from src.crawler import run_crawl

st.set_page_config(page_title="Scholarship Intelligence", page_icon="🎓", layout="wide")
init_db()

st.title("🎓 Scholarship Intelligence Crawler")
st.caption("Discover, extract, verify and monitor scholarship opportunities from source webpages.")
st.info("Only records with traceable primary-source evidence should be treated as verified. Search results are discovery hints, not evidence.")

with st.sidebar:
    st.header("Crawler controls")
    max_pages = st.slider("Maximum pages per run", min_value=5, max_value=150, value=40, step=5)
    if st.button("Run crawler now", type="primary", use_container_width=True):
        with st.spinner("Discovering and crawling pages. This may take several minutes..."):
            try:
                result = run_crawl(max_pages=max_pages)
                st.success(f"Run {result['run_id']} completed")
                st.json(result)
                st.rerun()
            except Exception as exc:
                st.error(f"Crawler failed: {exc}")
    st.markdown("---")
    st.markdown("**Run continuously from a terminal:**")
    st.code("python -m src.crawler --loop-hours 24", language="bash")

metrics = dashboard_metrics()
cols = st.columns(6)
metric_items = [
    ("Total discovered", metrics["total"]),
    ("Verified", metrics["verified"]),
    ("Review required", metrics["review_required"]),
    ("Active / expiring", metrics["active"]),
    ("Expired", metrics["expired"]),
    ("Avg. confidence", f"{metrics['average_confidence']}%")
]
for col, (label, value) in zip(cols, metric_items):
    col.metric(label, value)
st.caption(f"Records updated in the last 7 days: {metrics['recently_updated']}")

st.subheader("Scholarship records")
filters = st.columns([2, 1])
search_text = filters[0].text_input("Search by scholarship, provider or eligibility")
status_options = ["All", "ACTIVE", "EXPIRING_SOON", "EXPIRED", "REVIEW_REQUIRED", "NO_LONGER_VERIFIABLE"]
status_filter = filters[1].selectbox("Current status", status_options)
rows = list_scholarships(search_text=search_text, status=status_filter, limit=1000)

if not rows:
    st.warning("No records found yet. Run the crawler, or check the terminal output and crawl_errors table. The initial crawl depends on network access and source-site availability.")
else:
    table = pd.DataFrame([{
        "ID": r["id"], "Scholarship": r["name"], "Provider": r["provider"],
        "Benefit": r["amount_benefit"], "Deadline": r["closing_date"],
        "Current status": r["current_status"], "Verification": r["verification_status"],
        "Confidence": f"{r['confidence_score']:.1f}%", "Last verified": r["last_verified_at"]
    } for r in rows])
    st.dataframe(table, use_container_width=True, hide_index=True)

    selected_id = st.selectbox("Open scholarship details", [r["id"] for r in rows],
                               format_func=lambda value: next((f"{r['name']} (ID {r['id']})" for r in rows if r["id"] == value), str(value)))
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
            st.write("**Category criteria:**", record["category_criteria"])
            st.write("**Domicile criteria:**", record["domicile_criteria"])
            st.write("**Documents:**", record["documents_required"])
            st.write("**Selection:**", record["selection_process"])
            st.write("**Renewal:**", record["renewal_requirements"])
        with right:
            st.write("**Status:**", record["current_status"])
            st.write("**Verification:**", record["verification_status"])
            st.write("**Confidence:**", f"{record['confidence_score']:.1f}%")
            st.write("**Source type:**", record["source_type"])
            st.write("**Opening date:**", record["opening_date"])
            st.write("**Closing date:**", record["closing_date"])
            st.write("**Last verified:**", record["last_verified_at"])
            st.markdown(f"**Official source:** [{record['official_source_url']}]({record['official_source_url']})")
            if record["application_url"]:
                st.markdown(f"**Application link:** [{record['application_url']}]({record['application_url']})")
        with st.expander("Why this confidence score?"):
            reasons = json.loads(record["confidence_reasons"] or "[]")
            for reason in reasons:
                st.write("•", reason)
        with st.expander("Source evidence"):
            evidence = json.loads(record["evidence_json"] or "{}")
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

with st.expander("Recent crawl runs"):
    with connect() as conn:
        runs = pd.read_sql_query("SELECT * FROM crawl_runs ORDER BY id DESC LIMIT 20", conn)
        errors = pd.read_sql_query("SELECT * FROM crawl_errors ORDER BY id DESC LIMIT 20", conn)
    st.dataframe(runs, use_container_width=True, hide_index=True)
    st.markdown("**Recent crawl errors**")
    st.dataframe(errors, use_container_width=True, hide_index=True)

st.caption("Note: source websites may block automated requests or change their layout. Review records marked REVIEW REQUIRED before relying on them.")


# import os
# import sqlite3
# import pandas as pd
# import streamlit as st
# from config import DB_PATH
# from src.database import init_db
# from src.discovery import run_crawler_cycle

# # 1. Page Configuration
# st.set_page_config(
#     page_title="Atlas Funding - Scholarship Intelligence Engine",
#     page_icon="🎓",
#     layout="wide"
# )

# # 2. Automatically Initialize Database & Populate Initial Data on First Run
# init_db()

# conn = sqlite3.connect(DB_PATH)
# cursor = conn.cursor()
# cursor.execute("SELECT COUNT(*) FROM scholarships")
# count = cursor.fetchone()[0]
# conn.close()

# # Auto-run crawler cycle 1 if database has 0 records
# if count == 0:
#     run_crawler_cycle(1)

# # 3. Sidebar Controls
# st.sidebar.header("⚙️ Crawler Controls")
# run_choice = st.sidebar.selectbox("Select Crawler Run Version:", [1, 2])

# if st.sidebar.button("🚀 Run Auto-Crawler"):
#     with st.spinner(f"Running Crawler Cycle #{run_choice}..."):
#         logs = run_crawler_cycle(run_choice)
#         st.sidebar.success(f"Crawler Run #{run_choice} Completed!")
#         st.rerun()

# # 4. Load Data from SQLite Database
# conn = sqlite3.connect(DB_PATH)
# df = pd.read_sql_query("SELECT * FROM scholarships", conn)
# df_changes = pd.read_sql_query("SELECT * FROM change_history", conn)
# conn.close()

# # 5. Header Section
# st.title("🎓 Atlas Funding: Scholarship Intelligence Engine")
# st.markdown("Continuous Discovery, Verification, and Verification Engine for Indian Scholarships.")

# # 6. Top Metrics Dashboard
# if len(df) > 0:
#     col1, col2, col3, col4, col5 = st.columns(5)
#     col1.metric("Total Discovered", len(df))
#     col2.metric("Verified (≥95%)", len(df[df["verification_status"] == "VERIFIED"]))
#     col3.metric("Review Required", len(df[df["verification_status"] == "REVIEW REQUIRED"]))
#     col4.metric("Active", len(df[df["current_status"] == "ACTIVE"]))
#     avg_conf = df["confidence_score"].mean()
#     col5.metric("Avg Confidence", f"{avg_conf:.1f}%")

# st.divider()

# # 7. Main Interface Tabs
# tab1, tab2, tab3 = st.tabs(["📋 Scholarship Repository", "🔄 Change History Logs", "🛡️ Verification Engine Audit"])

# with tab1:
#     search_query = st.text_input("🔍 Search scholarships by name, provider, or state:", "")
    
#     if len(df) > 0:
#         filtered_df = df if not search_query else df[
#             df["name"].str.contains(search_query, case=False, na=False) |
#             df["provider"].str.contains(search_query, case=False, na=False)
#         ]
        
#         # Streamlit Dataframe display
#         st.dataframe(
#             filtered_df[[
#                 "name", "provider", "source_type", "amount_benefit", 
#                 "closing_date", "confidence_score", "verification_status", "current_status"
#             ]],
#             width="stretch"
#         )
        
#         st.divider()
        
#         # Detailed Record Inspector
#         st.subheader("🔍 Deep Record Inspector")
#         selected_name = st.selectbox("Select a scholarship to inspect details & evidence:", filtered_df["name"].tolist())
        
#         if selected_name:
#             row = filtered_df[filtered_df["name"] == selected_name].iloc[0]
            
#             c1, c2 = st.columns(2)
#             with c1:
#                 st.write(f"**Scholarship Name:** {row['name']}")
#                 st.write(f"**Provider:** {row['provider']}")
#                 st.write(f"**Source Type:** {row['source_type']}")
#                 st.write(f"**Official Source:** [{row['official_source_url']}]({row['official_source_url']})")
#                 st.write(f"**Application Link:** [{row['application_url']}]({row['application_url']})")
#                 st.write(f"**Income Criteria:** {row['income_criteria']}")
#             with c2:
#                 st.write(f"**Amount/Benefit:** {row['amount_benefit']}")
#                 st.write(f"**Academic Requirements:** {row['academic_req']}")
#                 st.write(f"**Closing Date:** {row['closing_date']}")
#                 st.write(f"**Current Status:** `{row['current_status']}`")
#                 st.write(f"**Confidence Score:** `{row['confidence_score']}%` ({row['verification_status']})")
            
#             st.info(f"**🛡️ Verification Source Evidence:** {row['source_evidence']}")

#     else:
#         st.warning("No scholarships found in the database. Click 'Run Auto-Crawler' in the sidebar!")

# with tab2:
#     st.subheader("🔄 Detected Updates & Versioning Logs")
#     if len(df_changes) > 0:
#         st.dataframe(df_changes, width="stretch")
#     else:
#         st.info("No changes detected yet. Select 'Run Version: 2' in the sidebar and click 'Run Auto-Crawler' to simulate deadline updates and change detection!")

# with tab3:
#     st.subheader("🛡️ Algorithmic Confidence Engine Rules")
#     st.markdown("""
#     - **+35 Points**: Source domain ends with official government or university suffix (`.gov.in`, `.edu.in`, `.ac.in`).
#     - **+20 Points**: Direct application portal link hosted on official government/educational domain.
#     - **+25 Points**: Core eligibility criteria (income, deadline, benefit) directly traceable in raw page text.
#     - **+20 Points**: Active status with a valid future deadline.
#     - **Threshold Rule**: Only records scoring **≥ 95.0%** confidence are assigned `VERIFIED` status. Anything lower is flagged as `REVIEW REQUIRED`.
#     """)