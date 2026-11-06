"""
Web Data Forge - Streamlit Studio UI
Interactive dashboard for configurable extraction, real-time safety inspection,
data quality scoring, and safe exports.
"""

import os
from pathlib import Path
import sys
import time
from typing import List

# Ensure package root 'src' is in sys.path when executed by Streamlit runner
src_dir = Path(__file__).resolve().parents[2]
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

import pandas as pd
import streamlit as st

from web_data_forge.core.exceptions import PlannerError
from web_data_forge.export import export_csv, export_json
from web_data_forge.inspection.url_validator import validate_url
from web_data_forge.models.contracts import (
    DataType,
    ExtractionPlan,
    FieldContract,
    PipelineResult,
)
from web_data_forge.orchestrator.pipeline import ExtractionPipeline
from web_data_forge.planner import AiPlanner, generate_heuristic_plan
from web_data_forge.quality import QualityAssessment, evaluate_quality
from web_data_forge.storage import (
    JobRepository,
    get_db_session,
    init_db,
)

# Initialize database schema
init_db()

# Set Page Configuration
st.set_page_config(
    page_title="Web Data Forge Studio",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling
st.markdown(
    """
    <style>
        .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
        .stMetric { background-color: rgba(255, 255, 255, 0.05); padding: 12px; border-radius: 8px; border: 1px solid rgba(255, 255, 255, 0.1); }
        .safety-badge-safe { color: #10B981; font-weight: 600; padding: 4px 8px; border-radius: 4px; background: rgba(16, 185, 129, 0.1); }
        .safety-badge-blocked { color: #EF4444; font-weight: 600; padding: 4px 8px; border-radius: 4px; background: rgba(239, 68, 68, 0.1); }
    </style>
    """,
    unsafe_allow_html=True,
)


def load_fixture_html() -> str:
    """Load local sample fixture HTML for offline testing."""
    root_dir = Path(__file__).resolve().parents[3]
    fixture_path = root_dir / "tests" / "fixtures" / "sample_product_page.html"
    if fixture_path.exists():
        return fixture_path.read_text(encoding="utf-8")
    return ""


# Header
col_header, col_badge = st.columns([3, 1])
with col_header:
    st.title("⚡ Web Data Forge Studio")
    st.caption("AI-assisted, configurable web data extraction, validation, and monitoring platform.")
with col_badge:
    st.write("")
    st.markdown(
        "<div style='text-align: right;'><span class='safety-badge-safe'>🛡️ SSRF Guard: STRICT</span></div>",
        unsafe_allow_html=True,
    )

st.divider()

# Sidebar: Configuration & Presets
st.sidebar.header("⚙️ Engine Configuration")

template_choice = st.sidebar.selectbox(
    "Load Preset Template:",
    ["Tech Products Catalog (Offline Fixture)", "Custom Target"],
    index=0,
)

st.sidebar.header("🤖 AI Planner Settings")
gemini_api_key = st.sidebar.text_input(
    "Gemini API Key:",
    type="password",
    value=os.environ.get("GEMINI_API_KEY", ""),
    help="Google Gemini API key for natural language plan translation.",
)
gemini_model = st.sidebar.selectbox(
    "Gemini Model:",
    ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"],
    index=0,
)

with st.sidebar.expander("🛡️ Network Security Bounds", expanded=False):
    timeout = st.slider("Request Timeout (seconds)", min_value=1.0, max_value=30.0, value=10.0, step=1.0)
    max_mb = st.slider("Max Download Size (MB)", min_value=1, max_value=20, value=5, step=1)
    max_bytes = max_mb * 1024 * 1024
    max_redirects = st.slider("Max Redirect Hops", min_value=0, max_value=10, value=5, step=1)
    sanitize_csv = st.checkbox("OWASP Formula Injection Defense", value=True, help="Neutralize spreadsheet formulas starting with =, +, -, @")

# Top-level Tabs
tab_studio, tab_history = st.tabs(["⚡ Extraction Studio", "📜 Job History & Datasets"])

with tab_studio:
    # Main Step 1: Target Definition
    st.subheader("1. Ingress Target & Scope")

    if template_choice == "Tech Products Catalog (Offline Fixture)":
        default_url = "https://example.com/store/tech-products"
        default_container = st.session_state.get("plan_container", ".product-card")
        is_offline_fixture = True
    else:
        default_url = "https://example.com"
        default_container = st.session_state.get("plan_container", "")
        is_offline_fixture = False

    col_url, col_status = st.columns([3, 1])

    with col_url:
        target_url = st.text_input("Target URL:", value=default_url, placeholder="https://example.com/...")

    with col_status:
        st.write("Target Safety Status:")
        if target_url:
            try:
                validate_url(target_url, verify_dns=False)
                st.markdown("<span class='safety-badge-safe'>✅ Scheme & Syntax Valid</span>", unsafe_allow_html=True)
            except Exception as e:
                st.markdown(f"<span class='safety-badge-blocked'>❌ Blocked: {e}</span>", unsafe_allow_html=True)

    # AI Planner Assistant
    with st.expander("✨ AI Extraction Planner (Natural Language)", expanded=True):
        col_ai_prompt, col_ai_opts = st.columns([3, 1])
        with col_ai_prompt:
            ai_prompt = st.text_input(
                "Natural Language Extraction Request:",
                value="Extract all products with title, price, rating, and product link",
                placeholder="e.g. Extract product title, price, rating, and product link",
            )
        with col_ai_opts:
            allow_fallback_opt = st.checkbox(
                "Allow Heuristic Fallback",
                value=True,
                help="Fall back to semantic DOM detection if API key is not provided or quota is exceeded.",
            )

        if st.button("🪄 Auto-Generate Plan with AI", type="secondary"):
            with st.spinner("Analyzing DOM and generating CSS selector plan..."):
                try:
                    if is_offline_fixture:
                        plan_html = load_fixture_html()
                    else:
                        from web_data_forge.security.network_guard import fetch_html
                        plan_html, _, _ = fetch_html(target_url, verify_dns=False, timeout=timeout)

                    planner = AiPlanner(
                        api_key=gemini_api_key or None,
                        model_name=gemini_model,
                    )
                    generated_plan = planner.plan_from_html(
                        user_instruction=ai_prompt,
                        html=plan_html,
                        target_url=target_url,
                        allow_fallback=allow_fallback_opt,
                    )

                    st.session_state["plan_container"] = generated_plan.container_selector or ""
                    st.session_state["plan_fields"] = [
                        {
                            "name": f.name,
                            "selector": f.selector,
                            "extract": f.extract,
                            "attr_name": f.attr_name or "",
                            "data_type": f.data_type.value if hasattr(f.data_type, "value") else str(f.data_type),
                            "regex": f.regex or "",
                            "required": f.required,
                        }
                        for f in generated_plan.fields
                    ]
                    st.success(f"Generated extraction plan with {len(generated_plan.fields)} fields!")
                    st.rerun()
                except PlannerError as err:
                    st.error(f"AI Planning Error: {err.message}")
                except Exception as err:
                    st.error(f"Failed to generate plan: {err}")

    col_mode, col_container = st.columns([1, 2])
    with col_mode:
        extraction_mode = st.radio(
            "Extraction Mode:",
            ["Repeated Items (Collection)", "Single Item / Page"],
            index=0 if default_container else 1,
        )

    with col_container:
        if extraction_mode == "Repeated Items (Collection)":
            container_selector = st.text_input(
                "Container CSS Selector:",
                value=default_container or ".item",
                help="CSS selector matching each item card / row.",
            )
        else:
            container_selector = None

    st.divider()

    # Main Step 2: Extraction Plan Builder
    st.subheader("2. Extraction Plan Studio")
    st.caption("Define CSS selectors and target types for each field. Null values are strictly reported—no hallucinated data.")

    if "plan_fields" in st.session_state:
        initial_fields = st.session_state["plan_fields"]
    elif template_choice == "Tech Products Catalog (Offline Fixture)":
        initial_fields = [
            {"name": "product_id", "selector": ".", "extract": "attr", "attr_name": "data-product-id", "data_type": "string", "regex": "", "required": True},
            {"name": "title", "selector": "h2.product-title", "extract": "text", "attr_name": "", "data_type": "string", "regex": "", "required": True},
            {"name": "price", "selector": ".product-price", "extract": "text", "attr_name": "", "data_type": "float", "regex": r"\$([\d.]+)", "required": False},
            {"name": "rating", "selector": ".product-rating", "extract": "text", "attr_name": "", "data_type": "float", "regex": "", "required": False},
            {"name": "review_count", "selector": ".review-count", "extract": "text", "attr_name": "", "data_type": "integer", "regex": r"\((\d[\d,]*)\s+reviews\)", "required": False},
            {"name": "out_of_stock", "selector": ".stock-badge.out-of-stock", "extract": "text", "attr_name": "", "data_type": "boolean", "regex": "", "required": False},
        ]
    else:
        initial_fields = [
            {"name": "title", "selector": "h1", "extract": "text", "attr_name": "", "data_type": "string", "regex": "", "required": True},
            {"name": "description", "selector": "p", "extract": "text", "attr_name": "", "data_type": "string", "regex": "", "required": False},
        ]

    # Field Editor
    edited_df = st.data_editor(
        pd.DataFrame(initial_fields),
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "name": st.column_config.TextColumn("Field Name", required=True),
            "selector": st.column_config.TextColumn("CSS Selector", required=True),
            "extract": st.column_config.SelectboxColumn("Extract Mode", options=["text", "attr", "html"], default="text"),
            "attr_name": st.column_config.TextColumn("Attribute Name (if attr)"),
            "data_type": st.column_config.SelectboxColumn("Data Type", options=["string", "integer", "float", "boolean", "url"], default="string"),
            "regex": st.column_config.TextColumn("Regex Pattern (optional)"),
            "required": st.column_config.CheckboxColumn("Required?", default=False),
        },
        key="fields_editor",
    )

    st.divider()

    # Main Step 3: Run Execution
    st.subheader("3. Pipeline Execution")

    run_clicked = st.button("🚀 Run Extraction Pipeline", type="primary", width="stretch")

    if run_clicked:
        # Build FieldContracts
        field_contracts: List[FieldContract] = []
        has_errors = False

        for idx, row in edited_df.iterrows():
            try:
                contract = FieldContract(
                    name=str(row["name"]).strip(),
                    selector=str(row["selector"]).strip(),
                    extract=str(row["extract"]).strip(),
                    attr_name=str(row["attr_name"]).strip() if str(row.get("attr_name", "")).strip() else None,
                    regex=str(row["regex"]).strip() if str(row.get("regex", "")).strip() else None,
                    data_type=DataType(str(row["data_type"]).strip()),
                    required=bool(row.get("required", False)),
                )
                field_contracts.append(contract)
            except Exception as exc:
                st.error(f"Row {idx + 1} ({row.get('name')}): {exc}")
                has_errors = True

        if not has_errors and field_contracts:
            try:
                plan = ExtractionPlan(
                    target_url=target_url,
                    container_selector=container_selector if extraction_mode == "Repeated Items (Collection)" else None,
                    fields=field_contracts,
                    timeout=timeout,
                    max_bytes=max_bytes,
                    max_redirects=max_redirects,
                )

                pipeline = ExtractionPipeline()

                with st.spinner("Executing extraction and security guardrails..."):
                    if is_offline_fixture:
                        sample_html = load_fixture_html()
                        result: PipelineResult = pipeline.run_offline(plan, sample_html)
                    else:
                        result = pipeline.run(plan, verify_dns=True)

                st.session_state["last_result"] = result

                # Auto-save extraction run to SQLite database
                try:
                    with get_db_session() as session:
                        repo = JobRepository(session)
                        saved_job = repo.save_job(result, quality=result.quality_assessment)
                        st.session_state["last_saved_job_id"] = saved_job.id
                except Exception as db_err:
                    st.warning(f"Could not persist run to database: {db_err}")

            except Exception as exc:
                st.error(f"Pipeline initialization failed: {exc}")

    # Display Results if Available
    if "last_result" in st.session_state:
        result: PipelineResult = st.session_state["last_result"]

        st.subheader("📊 Extraction Quality & Network Telemetry")

        if result.quality_assessment:
            qa: QualityAssessment = result.quality_assessment
            col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
            with col_m1:
                st.metric("Total Records", qa.total_records)
            with col_m2:
                st.metric("Composite Quality", f"{qa.quality_score:.1f}%", f"Grade {qa.quality_grade}")
            with col_m3:
                st.metric("Completeness", f"{qa.completeness_score:.1f}%")
            with col_m4:
                st.metric("Validity", f"{qa.validity_score:.1f}%")
            with col_m5:
                st.metric("Uniqueness", f"{qa.uniqueness_score:.1f}%")
        else:
            col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
            with col_m1:
                st.metric("Total Records", result.quality_report.total_records)
            with col_m2:
                st.metric("Valid Records", result.quality_report.valid_records)
            with col_m3:
                st.metric("Completeness", f"{result.quality_report.completeness_score}%")
            with col_m4:
                status_txt = f"{result.telemetry.status_code} OK" if result.telemetry.success else "Failed"
                st.metric("HTTP Status", status_txt)
            with col_m5:
                st.metric("Latency", f"{result.telemetry.latency_seconds}s")

        if st.session_state.get("last_saved_job_id"):
            st.caption(f"💾 *Persisted to SQLite database (Job ID: `{st.session_state['last_saved_job_id']}`)*")

        if not result.telemetry.success:
            st.error(f"Execution Error: {result.telemetry.error_message}")

        # Results Table
        st.subheader("📋 Collected Dataset")
        if result.records:
            df_records = pd.DataFrame(result.records)
            st.dataframe(df_records, use_container_width=True)

            # Safe Export Buttons
            st.subheader("📥 Safe Data Exports")
            col_csv, col_json, _ = st.columns([1, 1, 2])

            with col_csv:
                csv_data = export_csv(result.records, sanitize_formulas=sanitize_csv)
                st.download_button(
                    label="📄 Download Clean CSV",
                    data=csv_data,
                    file_name="extracted_data.csv",
                    mime="text/csv",
                    help="Formula-injection sanitized CSV file.",
                    width="stretch",
                )

            with col_json:
                json_data = export_json(result.records)
                st.download_button(
                    label="📦 Download JSON",
                    data=json_data,
                    file_name="extracted_data.json",
                    mime="application/json",
                    width="stretch",
                )

            # Audit Inspection
            with st.expander("🔍 Quality Audit & Missing Fields Breakdown"):
                if result.quality_assessment:
                    st.json(result.quality_assessment.model_dump())
                else:
                    st.json(result.quality_report.missing_fields_summary)
        else:
            st.info("No records extracted.")

# Tab 2: Job History & Datasets
with tab_history:
    st.subheader("📜 Extraction Job History")
    st.caption("All pipeline runs stored locally in SQLite with full telemetry and record snapshots.")

    try:
        with get_db_session() as session:
            repo = JobRepository(session)
            jobs = repo.list_jobs(limit=50)

            if not jobs:
                st.info("No saved extraction jobs yet. Run a pipeline in the Extraction Studio tab to start tracking.")
            else:
                total_jobs = len(jobs)
                avg_quality = round(sum(j.quality_score for j in jobs) / total_jobs, 1) if total_jobs > 0 else 0
                total_rec = sum(j.total_records for j in jobs)

                col_hj1, col_hj2, col_hj3 = st.columns(3)
                col_hj1.metric("Total Recorded Runs", total_jobs)
                col_hj2.metric("Average Quality Score", f"{avg_quality}%")
                col_hj3.metric("Total Records Collected", total_rec)

                st.divider()

                # Table of jobs
                jobs_data = [
                    {
                        "Job ID": j.id[:8] + "...",
                        "Timestamp (UTC)": j.created_at.strftime("%Y-%m-%d %H:%M:%S") if j.created_at else "",
                        "Target URL": j.target_url,
                        "Status": j.status,
                        "Records": j.total_records,
                        "Valid": j.valid_records,
                        "Grade": j.quality_grade,
                        "Quality": f"{j.quality_score:.1f}%",
                    }
                    for j in jobs
                ]
                st.dataframe(pd.DataFrame(jobs_data), use_container_width=True)

                st.subheader("🔍 Inspect & Export Past Job")
                job_options = {
                    f"{j.id[:8]}... | {j.target_url} ({j.created_at.strftime('%Y-%m-%d %H:%M') if j.created_at else ''})": j.id
                    for j in jobs
                }
                selected_label = st.selectbox("Select Job to Inspect:", list(job_options.keys()))
                selected_job_id = job_options[selected_label]

                selected_job = repo.get_job(selected_job_id)
                if selected_job:
                    past_records = repo.get_job_records(selected_job_id)
                    col_det1, col_det2 = st.columns(2)
                    with col_det1:
                        st.markdown(f"**Target URL:** `{selected_job.target_url}`")
                        st.markdown(f"**Quality Score:** {selected_job.quality_score}% (Grade **{selected_job.quality_grade}**)")
                    with col_det2:
                        st.markdown(f"**Status:** `{selected_job.status}` | **Records:** {selected_job.total_records}")
                        st.markdown(f"**Full Job UUID:** `{selected_job.id}`")

                    if past_records:
                        st.dataframe(pd.DataFrame(past_records), use_container_width=True)
                        col_dcsv, col_djson, col_del = st.columns([1, 1, 1])
                        with col_dcsv:
                            st.download_button(
                                "📄 Re-Download CSV",
                                data=export_csv(past_records, sanitize_formulas=True),
                                file_name=f"job_{selected_job.id[:8]}_export.csv",
                                mime="text/csv",
                                width="stretch",
                                key=f"dl_csv_{selected_job.id}",
                            )
                        with col_djson:
                            st.download_button(
                                "📦 Re-Download JSON",
                                data=export_json(past_records),
                                file_name=f"job_{selected_job.id[:8]}_export.json",
                                mime="application/json",
                                width="stretch",
                                key=f"dl_json_{selected_job.id}",
                            )
                        with col_del:
                            if st.button("🗑️ Delete Job", type="secondary", width="stretch", key=f"del_{selected_job.id}"):
                                repo.delete_job(selected_job.id)
                                st.success("Job deleted.")
                                st.rerun()
    except Exception as exc:
        st.error(f"Error accessing database: {exc}")

