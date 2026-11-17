"""
Web Data Forge - Streamlit Studio UI (Redesigned)
A beginner-friendly 3-step wizard: Enter URL → Describe What to Extract → Download Data.
Advanced controls are hidden in a collapsible "Expert Settings" section.
"""

import os
from pathlib import Path
import sys
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

# ─── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Web Data Forge",
    page_icon="⚡",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ─── Global Styles ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Cleaner page padding */
    .block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 860px; }

    /* Step badge */
    .step-badge {
        display: inline-block;
        background: #6366f1;
        color: white;
        font-size: 0.75rem;
        font-weight: 700;
        padding: 2px 10px;
        border-radius: 999px;
        margin-bottom: 4px;
        letter-spacing: 0.05em;
        text-transform: uppercase;
    }
    .step-title {
        font-size: 1.3rem;
        font-weight: 700;
        margin: 0 0 4px 0;
    }
    .step-hint {
        font-size: 0.88rem;
        color: #888;
        margin-bottom: 1rem;
    }

    /* URL status pills */
    .pill-ok  { color:#10B981; font-weight:600; background:rgba(16,185,129,.1); padding:3px 10px; border-radius:999px; font-size:0.85rem; }
    .pill-err { color:#EF4444; font-weight:600; background:rgba(239,68,68,.1); padding:3px 10px; border-radius:999px; font-size:0.85rem; }

    /* Quick example chips */
    .chip-row { display:flex; flex-wrap:wrap; gap:8px; margin:8px 0 16px 0; }
    .chip { background:#1e293b; border:1px solid #334155; border-radius:999px;
            padding:4px 14px; font-size:0.82rem; color:#94a3b8; cursor:pointer; }

    /* Result grade badge */
    .grade-A { color:#10B981; font-size:2rem; font-weight:800; }
    .grade-B { color:#84cc16; font-size:2rem; font-weight:800; }
    .grade-C { color:#facc15; font-size:2rem; font-weight:800; }
    .grade-F { color:#EF4444; font-size:2rem; font-weight:800; }

    /* Hide default streamlit footer & menu */
    #MainMenu {visibility:hidden;}
    footer {visibility:hidden;}
</style>
""", unsafe_allow_html=True)


# ─── Helpers ───────────────────────────────────────────────────────────────────
def load_fixture_html() -> str:
    """Load local sample fixture HTML for offline testing."""
    root_dir = Path(__file__).resolve().parents[3]
    fixture_path = root_dir / "tests" / "fixtures" / "sample_product_page.html"
    if fixture_path.exists():
        return fixture_path.read_text(encoding="utf-8")
    return ""


QUICK_EXAMPLES = [
    ("📚 Books",    "https://books.toscrape.com/",   "article.product_pod",  "Extract book title, price, and star rating"),
    ("💬 Quotes",   "https://quotes.toscrape.com/",  "div.quote",            "Extract quote text and author name"),
    ("📰 Hacker News", "https://news.ycombinator.com/", ".athing",           "Extract news headline and link"),
]

GRADE_CSS = {"A": "grade-A", "B": "grade-B", "C": "grade-C", "D": "grade-C", "F": "grade-F"}


def url_ok(url: str) -> bool:
    try:
        validate_url(url, verify_dns=False)
        return True
    except Exception:
        return False


# ─── Header ────────────────────────────────────────────────────────────────────
st.markdown("## ⚡ Web Data Forge")
st.markdown("<p style='color:#888;margin-top:-12px;'>Turn any website into a clean, downloadable dataset — no coding needed.</p>", unsafe_allow_html=True)
st.divider()


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 1 — Enter a Website URL
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown('<span class="step-badge">Step 1 of 3</span>', unsafe_allow_html=True)
st.markdown('<p class="step-title">🌐 Enter the website URL</p>', unsafe_allow_html=True)
st.markdown('<p class="step-hint">Paste the full address of the page you want to extract data from.</p>', unsafe_allow_html=True)

# --- Quick example buttons ---
st.markdown("**Try a quick example:**")
cols = st.columns(len(QUICK_EXAMPLES))
for i, (label, url, container, prompt) in enumerate(QUICK_EXAMPLES):
    if cols[i].button(label, key=f"ex_{i}", use_container_width=True):
        st.session_state["target_url"]        = url
        st.session_state["plan_container"]    = container
        st.session_state["ai_prompt"]         = prompt
        st.session_state.pop("plan_fields", None)   # reset any stale field plan
        st.session_state.pop("last_result", None)
        st.rerun()

# --- URL input ---
target_url = st.text_input(
    label="Website URL",
    value=st.session_state.get("target_url", ""),
    placeholder="https://quotes.toscrape.com/",
    label_visibility="collapsed",
)

if target_url:
    if url_ok(target_url):
        st.markdown('<span class="pill-ok">✅ URL looks good</span>', unsafe_allow_html=True)
        st.session_state["target_url"] = target_url
    else:
        st.markdown('<span class="pill-err">❌ Invalid or unsafe URL</span>', unsafe_allow_html=True)

st.divider()


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 2 — Describe What to Extract
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown('<span class="step-badge">Step 2 of 3</span>', unsafe_allow_html=True)
st.markdown('<p class="step-title">🤖 Describe what data you want</p>', unsafe_allow_html=True)
st.markdown('<p class="step-hint">Write in plain English what you want to extract. The AI will figure out the rest.</p>', unsafe_allow_html=True)

ai_prompt = st.text_area(
    label="What do you want to extract?",
    value=st.session_state.get("ai_prompt", "Extract the title, price, and author of each item"),
    placeholder="e.g. Extract the quote text and author name from every quote card",
    height=90,
    label_visibility="collapsed",
)

# Optional Gemini API key (friendly framing)
with st.expander("🔑 Use AI-powered extraction (optional — works without it too)"):
    st.caption("Paste your free Google Gemini API key to get smarter, more accurate field detection. Without it, a built-in rule-based engine is used automatically.")
    gemini_api_key = st.text_input(
        "Gemini API Key",
        type="password",
        value=os.environ.get("GEMINI_API_KEY", ""),
        placeholder="AIza...",
        label_visibility="collapsed",
    )

# ── Advanced / Expert Settings (hidden by default) ───────────────────────────
with st.expander("⚙️ Advanced settings — for experienced users"):
    st.caption("You can manually override what the AI detects below.")

    adv_col1, adv_col2 = st.columns(2)
    with adv_col1:
        container_selector_override = st.text_input(
            "Container CSS Selector",
            value=st.session_state.get("plan_container", ""),
            placeholder="e.g. div.quote or article.product_pod",
            help="The CSS selector that wraps each repeating item on the page.",
        )
    with adv_col2:
        gemini_model = st.selectbox(
            "AI Model",
            ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"],
            index=0,
        )

    timeout     = st.slider("Request Timeout (s)", 1.0, 30.0, 10.0, step=1.0)
    max_bytes   = st.slider("Max Page Size (MB)",   1,   20,   5) * 1024 * 1024
    max_redirects = st.slider("Max Redirect Hops",  0,   10,   5)
    sanitize_csv  = st.checkbox("OWASP CSV Formula Injection Defence", value=True)

    st.markdown("**Manual Field Definitions** *(overrides AI plan)*")

    if "plan_fields" in st.session_state:
        initial_fields = st.session_state["plan_fields"]
    else:
        initial_fields = []

    edited_df = st.data_editor(
        pd.DataFrame(initial_fields) if initial_fields else pd.DataFrame(columns=["name","selector","extract","attr_name","data_type","regex","required"]),
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "name":      st.column_config.TextColumn("Field Name",   required=True),
            "selector":  st.column_config.TextColumn("CSS Selector", required=True),
            "extract":   st.column_config.SelectboxColumn("Extract", options=["text","attr","html"], default="text"),
            "attr_name": st.column_config.TextColumn("Attribute (if attr)"),
            "data_type": st.column_config.SelectboxColumn("Data Type", options=["string","integer","float","boolean","url"], default="string"),
            "regex":     st.column_config.TextColumn("Regex (optional)"),
            "required":  st.column_config.CheckboxColumn("Required?", default=False),
        },
        key="fields_editor",
    )

st.divider()


# ═══════════════════════════════════════════════════════════════════════════════
#  STEP 3 — Extract & Download
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown('<span class="step-badge">Step 3 of 3</span>', unsafe_allow_html=True)
st.markdown('<p class="step-title">🚀 Extract & Download</p>', unsafe_allow_html=True)
st.markdown('<p class="step-hint">Hit the button below. We\'ll fetch the page, detect the data, and give you a clean file.</p>', unsafe_allow_html=True)

run_clicked = st.button("⚡ Extract Data Now", type="primary", use_container_width=True)

if run_clicked:
    # ── Validation ────────────────────────────────────────────────────────────
    if not target_url or not url_ok(target_url):
        st.error("Please enter a valid website URL in Step 1 first.")
        st.stop()

    with st.status("Working on it…", expanded=True) as status_box:

        # ── Determine container & fields ──────────────────────────────────────
        container_selector = container_selector_override.strip() if container_selector_override.strip() else None
        field_contracts: List[FieldContract] = []

        # Manual fields take priority if the user filled them in
        manual_rows = [r for _, r in edited_df.iterrows() if str(r.get("name","")).strip() and str(r.get("selector","")).strip()]

        if manual_rows:
            st.write("🔧 Using manually defined fields…")
            for idx, row in edited_df.iterrows():
                name_val = str(row.get("name", "")).strip()
                sel_val  = str(row.get("selector", "")).strip()
                if not name_val or not sel_val:
                    continue
                try:
                    field_contracts.append(FieldContract(
                        name=name_val,
                        selector=sel_val,
                        extract=str(row.get("extract","text")).strip(),
                        attr_name=str(row["attr_name"]).strip() if str(row.get("attr_name","")).strip() else None,
                        regex=str(row["regex"]).strip() if str(row.get("regex","")).strip() else None,
                        data_type=DataType(str(row.get("data_type","string")).strip()),
                        required=bool(row.get("required", False)),
                    ))
                except Exception as exc:
                    st.warning(f"Skipped row {idx+1} ({name_val}): {exc}")
        else:
            # ── AI / Heuristic planning ───────────────────────────────────────
            st.write("🤖 Analysing the page and auto-detecting fields…")
            try:
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
                    allow_fallback=True,
                )

                if not container_selector:
                    container_selector = generated_plan.container_selector

                field_contracts = list(generated_plan.fields)
                st.session_state["plan_container"] = container_selector or ""
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
                    for f in field_contracts
                ]
                st.write(f"✅ Detected **{len(field_contracts)}** fields: {', '.join(f'`{f.name}`' for f in field_contracts)}")
                st.write(f"🗂️ Container: `{container_selector}`")
            except PlannerError as err:
                st.error(f"Planning failed: {err.message}")
                st.stop()
            except Exception as err:
                st.error(f"Could not analyse the page: {err}")
                st.stop()

        if not field_contracts:
            st.error("No fields to extract. Please describe what data you want in Step 2.")
            st.stop()

        # ── Run pipeline ──────────────────────────────────────────────────────
        st.write("⚙️ Extracting data and validating quality…")
        try:
            plan = ExtractionPlan(
                target_url=target_url,
                container_selector=container_selector if container_selector else None,
                fields=field_contracts,
                timeout=timeout,
                max_bytes=max_bytes,
                max_redirects=max_redirects,
            )
            pipeline = ExtractionPipeline()
            result: PipelineResult = pipeline.run(plan, verify_dns=True)
            st.session_state["last_result"] = result

            # Persist to DB (silent on failure)
            try:
                with get_db_session() as session:
                    repo = JobRepository(session)
                    saved_job = repo.save_job(result, quality=result.quality_assessment)
                    st.session_state["last_saved_job_id"] = saved_job.id
            except Exception:
                pass

            status_box.update(label="Done! ✅", state="complete", expanded=False)
        except Exception as exc:
            st.error(f"Extraction failed: {exc}")
            st.stop()


# ═══════════════════════════════════════════════════════════════════════════════
#  RESULTS PANEL
# ═══════════════════════════════════════════════════════════════════════════════
if "last_result" in st.session_state:
    result: PipelineResult = st.session_state["last_result"]

    st.divider()
    st.markdown("### 📊 Results")

    # ── Summary scorecard ─────────────────────────────────────────────────────
    if result.quality_assessment:
        qa: QualityAssessment = result.quality_assessment
        grade = qa.quality_grade
        grade_css = GRADE_CSS.get(grade, "grade-F")

        col_grade, col_metrics = st.columns([1, 3])
        with col_grade:
            st.markdown(f'<div class="{grade_css}" style="text-align:center;padding:16px 0;">Grade<br>{grade}</div>', unsafe_allow_html=True)
        with col_metrics:
            m1, m2, m3 = st.columns(3)
            m1.metric("Records extracted", qa.total_records)
            m2.metric("Data completeness",  f"{qa.completeness_score:.0f}%")
            m3.metric("All records valid",  f"{qa.validity_score:.0f}%")
    else:
        total = result.quality_report.total_records
        st.metric("Records extracted", total)

    # ── No records warning ────────────────────────────────────────────────────
    if not result.records:
        st.warning(
            f"No data was found on this page. "
            f"The selectors may not match the page structure. "
            f"Try the **Advanced settings** above to adjust the Container CSS Selector "
            f"(currently: `{result.plan.container_selector or 'none'}`)."
        )

    # ── Data table ────────────────────────────────────────────────────────────
    else:
        df_records = pd.DataFrame(result.records)
        st.dataframe(df_records, use_container_width=True, height=300)

        # ── Download buttons ──────────────────────────────────────────────────
        st.markdown("#### 📥 Download Your Data")
        dl_col1, dl_col2 = st.columns(2)

        with dl_col1:
            csv_data = export_csv(result.records, sanitize_formulas=True)
            st.download_button(
                label="⬇️ Download as CSV (Excel-ready)",
                data=csv_data.encode("utf-8-sig"),
                file_name="extracted_data.csv",
                mime="text/csv",
                use_container_width=True,
                help="Opens cleanly in Microsoft Excel and Google Sheets.",
            )
        with dl_col2:
            json_data = export_json(result.records)
            st.download_button(
                label="⬇️ Download as JSON",
                data=json_data,
                file_name="extracted_data.json",
                mime="application/json",
                use_container_width=True,
                help="For developers — machine-readable structured data.",
            )

        # ── Reset ─────────────────────────────────────────────────────────────
        if st.button("🔄 Start a new extraction", use_container_width=False):
            for key in ["last_result", "last_saved_job_id", "plan_fields", "plan_container", "target_url", "ai_prompt"]:
                st.session_state.pop(key, None)
            st.rerun()

        # ── Expert: quality breakdown ─────────────────────────────────────────
        with st.expander("🔍 Detailed quality report"):
            if result.quality_assessment:
                st.json(result.quality_assessment.model_dump())
            else:
                st.json(result.quality_report.missing_fields_summary)


# ═══════════════════════════════════════════════════════════════════════════════
#  JOB HISTORY (bottom, collapsed)
# ═══════════════════════════════════════════════════════════════════════════════
st.divider()
with st.expander("📜 Extraction History"):
    try:
        with get_db_session() as session:
            repo = JobRepository(session)
            jobs = repo.list_jobs(limit=50)

            if not jobs:
                st.info("No extractions yet. Run your first extraction above!")
            else:
                jobs_data = [
                    {
                        "When":    j.created_at.strftime("%Y-%m-%d %H:%M") if j.created_at else "",
                        "Website": j.target_url,
                        "Records": j.total_records,
                        "Grade":   j.quality_grade,
                        "Quality": f"{j.quality_score:.0f}%",
                        "Status":  j.status,
                    }
                    for j in jobs
                ]
                st.dataframe(pd.DataFrame(jobs_data), use_container_width=True)

                # Inspect / re-download a past job
                st.markdown("**Re-download a past job:**")
                job_options = {
                    f"{j.created_at.strftime('%Y-%m-%d %H:%M') if j.created_at else ''} — {j.target_url} ({j.total_records} records, Grade {j.quality_grade})": j.id
                    for j in jobs
                }
                selected_label = st.selectbox("Select a past job:", list(job_options.keys()), label_visibility="collapsed")
                selected_job = repo.get_job(job_options[selected_label])
                if selected_job:
                    past_records = repo.get_job_records(selected_job.id)
                    if past_records:
                        hcol1, hcol2 = st.columns(2)
                        with hcol1:
                            st.download_button(
                                "⬇️ CSV",
                                data=export_csv(past_records, sanitize_formulas=True).encode("utf-8-sig"),
                                file_name=f"job_{selected_job.id[:8]}.csv",
                                mime="text/csv",
                                use_container_width=True,
                                key=f"h_csv_{selected_job.id}",
                            )
                        with hcol2:
                            st.download_button(
                                "⬇️ JSON",
                                data=export_json(past_records),
                                file_name=f"job_{selected_job.id[:8]}.json",
                                mime="application/json",
                                use_container_width=True,
                                key=f"h_json_{selected_job.id}",
                            )
                        if st.button("🗑️ Delete this job", key=f"del_{selected_job.id}"):
                            repo.delete_job(selected_job.id)
                            st.success("Deleted.")
                            st.rerun()
                    else:
                        st.info("No records stored for this job.")
    except Exception as exc:
        st.error(f"Could not load history: {exc}")
