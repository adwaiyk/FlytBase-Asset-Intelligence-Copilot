# ⚡ WellWise · FlytBase Asset Intelligence Copilot

[![MIT License](https://img.shields.io/badge/License-MIT-amber.svg)](LICENSE)
[![Hackathon](https://img.shields.io/badge/FlytBase%20Challenge-Hacktoberfest%20Pune%202026-blue.svg)](docs/SUBMISSION.md)
[![Model](https://img.shields.io/badge/Engine-Gemma%204%2031B%20(Open%20Weights)-emerald.svg)](https://openrouter.ai)
[![Dataset](https://img.shields.io/badge/Dataset-600%20Wells%20%7C%20125k%2B%20Inspections-purple.svg)](data/)
[![UI](https://img.shields.io/badge/UI-Streamlit%20SCADA%20%2B%20Next.js%2015-orange.svg)](app.py)

> **"Code computes, Gemma reasons."**  
> An autonomous industrial copilot that answers oilfield operators' plain-English questions **with deterministic precision, mathematical rigor, and cited evidence**. Built for the FlytBase Challenge at Hacktoberfest Hack Day Pune (17 Oct 2026).

---

## 🧭 Executive Summary

Oil and gas field operations generate mountains of heterogeneous data: SCADA telemetry, drone inspections, handheld FLIR readings, handwritten operator notes, regulatory compliance letters, and shifting SOPs/MOCs. 

**WellWise** replaces guesswork with a **deterministic semantic layer powered by Gemma 4**. When an operator asks a question, Gemma 4 decomposes the intent, calls deterministic query tools over an effective data view, dynamically audits compliance against rules extracted directly from engineering manuals, and renders generative UI components (status cards, timeseries charts, geospatial overlays, heatmaps).

<p align="center">
  <img src="static/logo-nav.png" alt="WellWise Asset Intelligence Copilot" width="180">
</p>

### 💡 Core Design Principles

1. **Zero Hallucination Arithmetic:** Every count, delta-temperature, downtime duration, and compliance check is computed in Python/DuckDB over real records. Gemma 4 writes the prose and plans the tools; it never invents numbers.
2. **Dynamic SOP & Rule Extraction:** Operational thresholds (e.g., T200 $\ge 15^\circ\text{C}$, T350 $\ge 20^\circ\text{C}$, T500 $\ge 25^\circ\text{C}$), MOC approval expirations, recall lot numbers, and response deadlines are extracted at runtime from SOP documents into an inheritance-aware rule registry.
3. **Effective View with Human-in-the-Loop Feedback:** Field corrections, work order overrides, and disputed spill statuses are stored as auditable assertions (`applied`, `unconfirmed`, or `disputed`) that immediately update calculations across all subsequent user sessions.
4. **Role-Scoped & Isolated Memory:** Each operator has private session history and user preferences (e.g. custom sorting or unit preferences), while verified operational facts and corrections are shared across the entire field team.
5. **Cost-Efficient Industrial Scale:** Powered by open-weights Gemma 4 via OpenRouter with local SQLite response caching. Total inference cost: **$0.00**.

---

## 🏛️ System Architecture

```
                                  ┌──────────────────────────────────────────────┐
                                  │           INDUSTRIAL OPERATOR INTERFACES     │
                                  ├───────────────────────┬──────────────────────┤
                                  │ Streamlit SCADA OS    │ Next.js 15 + shadcn  │
                                  │ (app.py)              │ (web/ app router)    │
                                  └───────────┬───────────┴──────────┬───────────┘
                                              │                      │
                                              ▼                      ▼
                                     ┌─────────────────────────────────┐
                                     │   BFF / FastAPI Auth & Session  │
                                     │  (PBKDF2-SHA256, 256-bit token) │
                                     └────────────────┬────────────────┘
                                                      │
                       ┌──────────────────────────────┴──────────────────────────────┐
                       ▼                                                             ▼
     ┌───────────────────────────────────┐                         ┌───────────────────────────────────┐
     │    GEMMA 4 REASONING HARNESS      │                         │     DETERMINISTIC SEMANTIC LAYER  │
     │    (copilot/agent.py + llm.py)    │                         │       (copilot/engine.py)         │
     ├───────────────────────────────────┤                         ├───────────────────────────────────┤
     │ • Intent Planning & Multi-Turn    │ ─── Tool Calls (26) ──▶ │ • DuckDB / Pandas In-Memory       │
     │ • Generative UI Visual Picker     │ ◀── Structured Data ─── │ • Raw Data ⊕ Feedback Overlay     │
     │ • Cited Natural Language Response │                         │ • BM25 SOP / Manuals Text Index   │
     │ • OpenRouter Gemma 4 31B / 26B    │                         │ • Dynamic Rule Inheritance Engine │
     └───────────────────────────────────┘                         └─────────────────┬─────────────────┘
                                                                                     │
                                   ┌─────────────────────────────────────────────────┴──┐
                                   ▼                                                    ▼
                     ┌───────────────────────────┐                        ┌───────────────────────────┐
                     │   DATASETS (600 WELLS)    │                        │  PERSISTENT SQLITE STORE  │
                     │ (data/flytbase-dataset/)  │                        │      (copilot.db)         │
                     ├───────────────────────────┤                        ├───────────────────────────┤
                     │ • 125,000+ Inspections    │                        │ • User Accounts & Roles   │
                     │ • 17,000+ Repairs (MD)    │                        │ • Scoped Conversations    │
                     │ • 1,900+ Operator Notes   │                        │ • Shared Assertions & Log │
                     │ • Fleet Metadata & SOPs   │                        │ • Episodic Memory & Prefs │
                     └───────────────────────────┘                        └───────────────────────────┘
```

---

## ⚡ Key Features

| Capability | Technical Implementation |
|---|---|
| **SCADA Telemetry HUD** | Real-time fleet metrics (active wells, shut-in assets, thermal compliance rate, open fines, auto-detected clock anchor). |
| **Generative SCADA UI** | Auto-binds components based on query: well status cards, interactive Plotly timeseries, PyDeck geospatial overlays, and compliance audit tables. |
| **SOP Protocol Auditing** | Verifies gas leaks under OPS-1 (24h/12h response thresholds), bypasses under OPS-2 / MOC-031 / MOC-036 / MOC-044, and cold-weather checks under OPS-5. |
| **Conflict & Dispute Engine** | Flags contradictory data (e.g. handheld FLIR gun vs telemetry, unconfirmed operator chatter, disputed oil spills). |
| **Multi-Turn Persistent Chat** | Maintains state across turns with role-scoped memory and cross-session fact sharing. |
| **Enterprise Security** | PBKDF2-SHA256 password hashing (200k rounds), constant-time comparisons, server-side session tokens, and brute-force lockout. |

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10+ (tested on Windows & Linux)
- Node.js 18+ (for Next.js frontend, optional)
- An [OpenRouter API Key](https://openrouter.ai) with access to Gemma 4 free models

### 1. Clone & Setup Environment

```bash
git clone https://github.com/adwaiyk/FlytBase-Asset-Intelligence-Copilot.git
cd FlytBase-Asset-Intelligence-Copilot

# Create and activate virtual environment
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
```

Edit `.env` and set your `OPENROUTER_API_KEY`:
```ini
OPENROUTER_API_KEY=your_openrouter_key_here
COPILOT_MODEL=google/gemma-4-31b-it:free
COPILOT_DATA_DIRS=test-data/dataset
```

### 2. Verify Data Ingestion

Check loaded wells, areas, extracted rules, and current temporal anchor:
```bash
python -m copilot.cli info
```

---

## 🖥️ Running the Application

### Option A: Streamlit Cyber-Industrial OS (Recommended)
Launch the interactive SCADA command center with built-in operator switching, quick evaluation triggers, and thermal vision override:

```bash
streamlit run app.py
```
> **URL:** `http://localhost:8501`  
> **Default credentials:** Sign in using any user from `fleet/users.json` (e.g. `Robert Hayes`, `Nathan Pierce`, `Olivia Grant`, `Michael Turner`) with default password: `flytbase2026`.

### Option B: Full-Stack Next.js 15 Web App
Launch the decoupled Next.js + FastAPI enterprise stack:

```bash
# Terminal 1: FastAPI Backend
uvicorn copilot.server:app --port 8000

# Terminal 2: Next.js Frontend
cd web
npm install
npm run build
npm start
```
> **URL:** `http://localhost:3000`

### Option C: Headless Evaluation CLI
Run automated evaluations directly from the command line:

```bash
# Run the 11 final evaluation questions (21 turns across multiple operators)
python -m copilot.cli run eval/final.json --out results-final.md --db /tmp/final.db

# Ask a one-off question as a specific operator
python -m copilot.cli ask --user U-201 "Is WELL-0001 producing oil right now?"
```

---

## 🧪 Comprehensive Automated Tests

Verify engine calculations, SOP auditing, security, and privacy without consuming API quota:

```bash
python -m pytest -q tests
```

Tests cover:
- Deterministic production status determination across T200, T350, and T500 well types
- Regulatory spill response deadlines (SR-01, SR-02, SR-03)
- Temporary bypass validity vs active MOC memos
- Scoped memory isolation between operators
- Password hashing, session expiry, and brute-force lockout

---

## 📊 Final Evaluation Results (Test Dataset · 600 Wells · 15 Jan 2027)

Summary of results verified against ground-truth records across all 11 final challenge scenarios:

| # | Scenario & Query | Verified Findings |
|---|---|---|
| **Q1** | **Reservoir Pressure Map** | **Honest Grounding:** No reservoir pressure exists in inspection telemetry or maintenance logs. The copilot clearly states the limitation instead of hallucinating. |
| **Q2** | **Best Oil Producer in 2026** | **Proxy Reasoning:** Cumulative volume is unrecorded. Using producing uptime as an honest proxy, multiple wells tie at 53/53 weeks (e.g., `WELL-0051`, `WELL-0530`, `WELL-0536`). |
| **Q3** | **Gas Leak Reports (OPS-1)** | **26 Reports Audited:** 17 met response deadlines, 9 missed. Identifies specific breaches (e.g. `WELL-0163` took 251h vs 24h limit; `WELL-0332` had no response). |
| **Q4** | **Temporary Flowline Bypasses (OPS-2)** | **Active Bypasses:** `WELL-0248` (Allowed via MOC-031/044), `WELL-0249` (Expired 15 Dec 2026), `WELL-0405` (Not approved). Uncovers historical unapproved bypasses. |
| **Q5** | **Regulator Letter Compliance** | **6 Spills Evaluated:** 3 compliant, 3 non-compliant (`WELL-0123`, `WELL-0182`, `WELL-0262`) due to missing mandatory post-cleanup soil laboratory sampling. |
| **Q6** | **Inspection vs Operator Discrepancies** | **15 Wells Reconciled:** Uses recency and SOP rules to adjudicate status. E.g. flags unconfirmed restarts vs confirmed shut-ins. |
| **Q7** | **Predictive Maintenance Ranking** | Cross-references acoustic anomalies ("rattling", "fluid pound", "hunting amps") in operator notes against subsequent repairs to rank top 10 failure risks. |
| **Q8** | **Cross-User Memory & Attribution** | Records Nathan's pump swap assertion as shared knowledge while keeping sorting preferences private. Correctly flags Olivia's hearsay as *unconfirmed*. |
| **Q9** | **Multi-Topic Conversational Context** | Audits remaining recalled pumps (9 units), identifies Northwest leadership, evaluates sub-zero heat-trace checks (OPS-5), and tracks well status across shifts. |
| **Q10** | **Shut-in Delay Root Cause Analysis** | **251 Delayed Jobs:** Parts (117), Contractors (76), Crews (58). Identifies Southeast Block 31 as a crew delay outlier (20-day median). Generates stacked bar chart. |
| **Q11** | **Thermal Anomaly Region** | **Southeast Block 31 Identified:** Wellheads average 31.5 °C above ambient (vs 26–29 °C elsewhere), confirmed as asset-driven rather than weather-related. |

*Full evaluation write-up and analysis available in [`docs/SUBMISSION.md`](docs/SUBMISSION.md) and [`docs/RESULTS_PAGE_2.md`](docs/RESULTS_PAGE_2.md).*

---

## 📂 Repository Structure

```
FlytBase-Asset-Intelligence-Copilot/
├── app.py                     # Streamlit Palantir/SCADA Cyber-Industrial Dashboard
├── copilot/                   # Core Python Intelligence Engine
│   ├── agent.py               # Gemma 4 Agent Harness, planning, visual policy
│   ├── cli.py                 # Command line runner for evaluations & queries
│   ├── config.py              # Environment configuration & path resolution
│   ├── data.py                # Ingestion, repair parser, BM25 index, SOP registry
│   ├── engine.py              # 26 deterministic DuckDB tools & semantic queries
│   ├── feedback.py            # Conflict engine, assertions, corrections overlay
│   ├── llm.py                 # OpenRouter API client, fallback models, SQLite cache
│   ├── render.py              # Generative visual components & rendering helpers
│   ├── server.py              # FastAPI backend for Next.js BFF
│   └── store.py               # SQLite user accounts, sessions, private/shared memory
├── data/                      # Dataset repository (600 wells, inspections, SOPs)
├── docs/                      # Architecture, System Design & Submission Documentation
│   ├── SUBMISSION.md          # Official Hackathon 2-page submission write-up
│   ├── SYSTEM_DESIGN.md       # Comprehensive deep-dive architecture document
│   └── RESULTS_PAGE_2.md      # Detailed breakdown of final question evaluations
├── eval/                      # Evaluation datasets (final.json, examples.json)
├── static/                    # PWA assets, icons, base64 navbar logo
├── tests/                     # Deterministic test suite (engine, auth, SOP audits)
├── web/                       # Next.js 15 + shadcn/ui alternate frontend
├── requirements.txt           # Python package requirements
└── README.md                  # Project documentation
```

---

## 👥 Authors & Team

Developed with ❤️ for **FlytBase Hacktoberfest Hack Day Pune (17 October 2026)**.

- **License:** [MIT License](LICENSE)
- **Challenge:** FlytBase Asset Intelligence Copilot
