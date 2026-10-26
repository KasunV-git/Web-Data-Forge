"""
Web Data Forge - Streamlit Studio UI
Interactive dashboard for configurable extraction, real-time safety inspection,
data quality scoring, and safe exports.
"""

from pathlib import Path
import time
from typing import List
import pandas as pd
import streamlit as st

from web_data_forge.export import export_csv, export_json
from web_data_forge.inspection.url_validator import validate_url
from web_data_forge.models.contracts import (
    DataType,
    ExtractionPlan,
    FieldContract,
    PipelineResult,
)
from web_data_forge.orchestrator.pipeline import ExtractionPipeline

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

with st.sidebar.expander("🛡️ Network Security Bounds", expanded=False):
    timeout = st.slider("Request Timeout (seconds)", min_value=1.0, max_value=30.0, value=10.0, step=1.0)
    max_mb = st.slider("Max Download Size (MB)", min_value=1, max_value=20, value=5, step=1)
    max_bytes = max_mb * 1024 * 1024
    max_redirects = st.slider("Max Redirect Hops", min_value=0, max_value=10, value=5, step=1)
    sanitize_csv = st.checkbox("OWASP Formula Injection Defense", value=True, help="Neutralize spreadsheet formulas starting with =, +, -, @")

# Main Step 1: Target Definition
st.subheader("1. Ingress Target & Scope")

if template_choice == "Tech Products Catalog (Offline Fixture)":
    default_url = "https://example.com/store/tech-products"
    default_container = ".product-card"
    is_offline_fixture = True
else:
    default_url = "https://example.com"
    default_container = ""
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

if template_choice == "Tech Products Catalog (Offline Fixture)":
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

run_clicked = st.button("🚀 Run Extraction Pipeline", type="primary", use_container_width=True)

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

        except Exception as exc:
            st.error(f"Pipeline initialization failed: {exc}")

# Display Results if Available
if "last_result" in st.session_state:
    result: PipelineResult = st.session_state["last_result"]

    # Telemetry and Quality Scorecard
    st.subheader("📊 Extraction Quality & Network Telemetry")

    col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
    with col_m1:
        st.metric("Total Records", result.quality_report.total_records)
    with col_m2:
        st.metric("Valid Records", result.quality_report.valid_records)
    with col_m3:
        st.metric("Quality Completeness", f"{result.quality_report.completeness_score}%")
    with col_m4:
        status_txt = f"{result.telemetry.status_code} OK" if result.telemetry.success else "Failed"
        st.metric("HTTP Status", status_txt)
    with col_m5:
        st.metric("Latency", f"{result.telemetry.latency_seconds}s")

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
                use_container_width=True,
            )

        with col_json:
            json_data = export_json(result.records)
            st.download_button(
                label="📦 Download JSON",
                data=json_data,
                file_name="extracted_data.json",
                mime="application/json",
                use_container_width=True,
            )

        # Audit Inspection
        with st.expander("🔍 Quality Audit & Missing Fields Breakdown"):
            st.json(result.quality_report.missing_fields_summary)
    else:
        st.info("No records extracted.")
