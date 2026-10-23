# Web Data Forge

**AI-assisted, configurable web data extraction, validation, and monitoring platform.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status: Foundation](https://img.shields.io/badge/Status-Week%201%20Foundation-orange.svg)](#roadmap)

Web Data Forge is an explainable data pipeline that translates natural-language extraction instructions into typed extraction plans, safely inspects targets, executes bounded extraction, validates collected fields against schema contracts, and produces clean CSV/JSON datasets.

---

## Key Features & Differentiators

- **Explainable Pipeline**: Natural language request &rarr; typed schema &rarr; safe source inspection &rarr; extraction adapter &rarr; evidence-backed validation &rarr; exported dataset.
- **Robust Security & SSRF Defenses**: Pre-fetch destination validation blocking loopback (`127.0.0.1`), private RFC1918 networks, link-local, multicast, and cloud metadata endpoints (`169.254.169.254`). Revalidation of all HTTP redirect targets.
- **Ethical Extraction Guardrails**: Respects `robots.txt` crawler guidance and HTTP rate limit signals (`429 Retry-After`). Strict resource boundaries on response bytes, timeouts, and concurrency. Does not bypass logins, paywalls, or CAPTCHAs.
- **Strict Data Contracts**: Powered by Pydantic v2 schemas. Missing values are explicitly recorded as missing—no hallucinated or fabricated data points.
- **Safe Serialization**: Neutralizes spreadsheet formula-injection (`=`, `@`, `+`, `-`) in CSV exports.

---

## Architecture & Technology Stack

| Component | Technology | Rationale |
| :--- | :--- | :--- |
| **Language** | Python 3.11+ | Industry standard for data engineering, scraping, and testing. |
| **Schemas** | Pydantic v2 | Strictly typed contracts for requests, plans, and extracted records. |
| **Static Extractor** | Requests + BeautifulSoup4 | Fast, deterministic HTML extraction with size & timeout bounds. |
| **AI Planner** | Google Gemini (via adapter) | Natural-language request translation into typed field specifications. |
| **Storage** | SQLite + SQLAlchemy | Lightweight local persistence moving to PostgreSQL when deployed. |
| **Dashboard UI** | Streamlit | Clean, reactive user interface with strict separation from business logic. |
| **Packaging & CI** | Docker + GitHub Actions | Reproducible runtime, non-root execution, and automated test suite. |

---

## Project Structure (Modular Monolith)

```
web-data-forge/
├── .env.example              # Environment variables template
├── .gitignore                # Git ignore rules for virtual environments, secrets, databases
├── pyproject.toml            # Project packaging metadata and pytest configuration
├── requirements.txt          # Pinned runtime dependencies
├── README.md                 # Project documentation and specifications
├── src/
│   └── web_data_forge/       # Core Python package namespace
│       └── __init__.py
├── tests/
│   ├── conftest.py           # Shared test fixtures
│   └── test_smoke.py         # Baseline smoke tests
└── data/                     # Local storage directory (git-tracked via .gitkeep)
```

---

## Getting Started

### 1. Prerequisites
- Python 3.11 or higher
- Git

### 2. Setup Virtual Environment
```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/Web-Data-Forge.git
cd Web-Data-Forge

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Linux/macOS:
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
```bash
cp .env.example .env
# Edit .env and supply your GEMINI_API_KEY when AI planning is enabled
```

### 5. Run Tests
```bash
pytest
```

---

## Security & Ethical Principles

1. **Authorization**: Web Data Forge requires users to have permission to access submitted URLs. Automated tooling does not confer legal authorization.
2. **Untrusted Content**: HTML, scraped text, and metadata are untrusted data. They are never executed, passed directly to shell commands, or used to manipulate AI tool boundaries.
3. **SSRF Controls**: All requests resolve hostnames and verify IP destinations against private and reserved IP blocks prior to socket connection.
4. **No Secret Commitments**: API keys and environment files must never be committed to git.

---

## Roadmap

- [x] **Week 1: Project Foundation** &mdash; Base configuration, skeleton, smoke tests, documentation.
- [ ] **Week 2: URL Safety & Static Extraction** &mdash; SSRF defense, Requests/BS4 parser, HTML fixtures.
- [ ] **Week 3: Core Orchestrator** &mdash; Pydantic data contracts, pipeline coordination.
- [ ] **Week 4: Streamlit UI & Safe Exports (MVP)** &mdash; Form input, results table, CSV/JSON downloads.
- [ ] **Week 5: AI Planner** &mdash; Gemini API adapter, schema validation, manual fallback.
- [ ] **Week 6: Quality & Storage** &mdash; Quality reporting, SQLite persistence with SQLAlchemy.
- [ ] **Week 7: Hardening, CI & Docker** &mdash; Dockerfile, docker-compose, GitHub Actions.
- [ ] **Week 8: Portfolio Polish** &mdash; Architecture diagram, benchmark corpus, demo release.

---

## License
MIT License. See [LICENSE](LICENSE) for details.
