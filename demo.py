"""
Web Data Forge - Standalone Interactive Terminal Demo
Demonstrates end-to-end web data extraction, multi-dimensional quality scoring,
OWASP formula-injection safe export, and SQLite persistence.

Usage:
    python demo.py
"""

from pathlib import Path
import sys
import time

# Reconfigure stdout for utf-8 on Windows terminals
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure src is in python path
src_dir = Path(__file__).resolve().parent / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from web_data_forge.export import export_csv, export_json
from web_data_forge.inspection.url_validator import validate_url
from web_data_forge.models.contracts import DataType, ExtractionPlan, FieldContract
from web_data_forge.orchestrator.pipeline import ExtractionPipeline
from web_data_forge.quality import QualityAssessment
from web_data_forge.storage import JobRepository, get_db_session, init_db


# ANSI Color Codes for Terminal Output
GREEN = "\033[92m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_banner():
    banner = f"""
{CYAN}{BOLD}======================================================================
  WEB DATA FORGE - Explainable Data Extraction Platform
======================================================================{RESET}
  AI-assisted, configurable web data extraction, validation & monitoring
"""
    print(banner)


def main():
    print_banner()

    # Step 1: Ingress & SSRF Security Check
    target_url = "https://example.com/store/tech-hardware"
    print(f"{BOLD}[Step 1/5]{RESET} Ingress Target Definition & SSRF Defense Guard")
    print(f"  Target URL: {CYAN}{target_url}{RESET}")

    try:
        validate_url(target_url, verify_dns=False)
        print(f"  SSRF Pre-check: {GREEN}[OK] PASSED (Restricted IP blocks & scheme valid){RESET}\n")
    except Exception as exc:
        print(f"  SSRF Pre-check: \033[91m[X] BLOCKED: {exc}{RESET}")
        return

    # Step 2: Define Extraction Plan & Typed Contracts
    print(f"{BOLD}[Step 2/5]{RESET} Building Pydantic v2 Extraction Plan")
    plan = ExtractionPlan(
        target_url=target_url,
        container_selector="article.product-item",
        fields=[
            FieldContract(name="sku", selector=".", extract="attr", attr_name="data-sku", required=True),
            FieldContract(name="title", selector="h3.item-name", required=True),
            FieldContract(name="price", selector="span.price-val", required=True),
            FieldContract(name="rating", selector="span.stars", data_type=DataType.FLOAT, required=False),
            FieldContract(name="reviews", selector="span.review-total", regex=r"\((\d[\d,]*)\s+reviews\)", data_type=DataType.INTEGER, required=False),
            FieldContract(name="stock", selector="span.stock-status", required=True),
        ],
    )
    print(f"  Container Selector: {CYAN}{plan.container_selector}{RESET}")
    print(f"  Configured Fields: {len(plan.fields)} contracts ({', '.join(f.name for f in plan.fields)})\n")

    # Step 3: Execute Extraction Pipeline
    print(f"{BOLD}[Step 3/5]{RESET} Executing Extraction Pipeline (Offline Benchmark Fixture)")
    fixture_path = Path(__file__).resolve().parent / "tests" / "fixtures" / "benchmark" / "ecommerce_catalog.html"
    if not fixture_path.exists():
        # Fallback to standard product fixture
        fixture_path = Path(__file__).resolve().parent / "tests" / "fixtures" / "sample_product_page.html"

    html_content = fixture_path.read_text(encoding="utf-8")

    pipeline = ExtractionPipeline()
    start_time = time.perf_counter()
    result = pipeline.run_offline(plan, html_content)
    elapsed = (time.perf_counter() - start_time) * 1000

    print(f"  Extraction Status: {GREEN}[OK] SUCCESS{RESET}")
    print(f"  Records Extracted: {BOLD}{len(result.records)}{RESET}")
    print(f"  Execution Latency: {CYAN}{elapsed:.2f} ms{RESET}\n")

    # Display Extracted Records Table
    print(f"{BOLD}Extracted Records Preview:{RESET}")
    print("-" * 75)
    for idx, r in enumerate(result.records, 1):
        print(f"  {idx}. {r.get('title')}")
        print(f"     Price: {r.get('price')} | Rating: {r.get('rating')} | Reviews: {r.get('reviews')} | Stock: {r.get('stock')}")
    print("-" * 75 + "\n")

    # Step 4: Multi-Dimensional Quality Evaluation
    print(f"{BOLD}[Step 4/5]{RESET} Multi-Dimensional Data Quality Scorecard")
    qa: QualityAssessment = result.quality_assessment
    grade_color = GREEN if qa.quality_grade in ("A", "B") else YELLOW
    print(f"  Composite Quality Score: {grade_color}{BOLD}{qa.quality_score:.1f}% (Grade: {qa.quality_grade}){RESET}")
    print(f"    - Completeness Score: {qa.completeness_score:.1f}% ({qa.total_fields_collected}/{qa.total_fields_expected} fields)")
    print(f"    - Schema Validity:    {qa.validity_score:.1f}% ({qa.valid_records}/{qa.total_records} valid records)")
    print(f"    - Uniqueness Score:   {qa.uniqueness_score:.1f}% ({qa.duplicate_records} duplicates detected)\n")

    # Step 5: Persistent Storage & Safe Export
    print(f"{BOLD}[Step 5/5]{RESET} SQLite Persistence & OWASP Formula-Injection Safe Export")
    init_db()
    with get_db_session() as session:
        repo = JobRepository(session)
        job = repo.save_job(result, quality=qa)
        saved_id = job.id

    print(f"  Database Storage: {GREEN}[OK] SAVED{RESET} (Job UUID: {CYAN}{saved_id}{RESET})")

    csv_data = export_csv(result.records, sanitize_formulas=True)
    json_data = export_json(result.records)

    print(f"\n{BOLD}Sanitized RFC 4180 CSV Preview:{RESET}")
    print(csv_data.strip())

    print(f"\n{GREEN}{BOLD}[OK] DEMO EXECUTION COMPLETE!{RESET}")
    print(f"Launch the interactive Streamlit Studio: {CYAN}python run_app.py{RESET}")
    print(f"Or launch via Docker:                     {CYAN}docker compose up --build{RESET}\n")


if __name__ == "__main__":
    main()
