# WellWise · FlytBase Asset Intelligence Copilot

A chat copilot that answers operators' plain-English questions about an oil field, **correctly and with evidence**, built for the FlytBase challenge at Hacktoberfest Hack Day Pune (17 Oct 2026). Powered by **Gemma 4** through OpenRouter.

**Design:** Gemma 4 plans, calls tools, picks the visual and writes the answer; a deterministic semantic layer computes every number over the data *with corrections applied*. Full design: [`docs/SYSTEM_DESIGN.md`](docs/SYSTEM_DESIGN.md).

## Quick start

```bash
pip install -r requirements.txt
./scripts/fetch_data.sh                 # clones the dataset into data/flytbase-dataset
cp .env.example .env                    # put your OPENROUTER_API_KEY in .env
python -m copilot.cli info              # what was loaded: wells, areas, rules extracted from manuals, "today"
streamlit run app.py                    # UI; sign in as any user (default password in .env)
```

Load the test dataset **alongside** the sample:

```bash
COPILOT_DATA_DIRS=data/flytbase-dataset/sample-data,data/test-data python -m copilot.cli info
```

Run a scripted multi-user scenario and write a results page:

```bash
python -m copilot.cli run eval/examples.json --out results.md --db /tmp/eval.db
python -m copilot.cli ask --user U-201 "Is WELL-0001 producing oil right now?"
```

Tests (no model needed): `python -m pytest -q tests`

## What's inside

| Module | Role |
|---|---|
| `copilot/data.py` | Ingestion of any number of dataset folders; repair-report parser (containment time, compliance table, stated spill class); **rules registry extracted from the manuals/SOPs** with inheritance (T350 → T200); BM25 document index |
| `copilot/engine.py` | Semantic layer: effective view (raw ⊕ applied corrections, originals kept) and tools: `well_snapshot`, `fleet_status`, `timeseries`, `downtime`, `spills`, `compliance_audit`, `repairs`, `rca_candidates`, `well_notes`, `search_docs`, `get_rules`, `run_sql` |
| `copilot/feedback.py` | Write path: corrections to raw data and AI analysis, scoped rules, shared well facts; resolves the record in code; conflict engine (applied / unconfirmed / disputed) |
| `copilot/store.py` | SQLite: user accounts (PBKDF2 passwords, session tokens), **private conversations and messages per user**, episodic memory, shared assertion store |
| `copilot/agent.py` | Harness: context assembly, Gemma 4 tool loop, visual policy, grounding check, memory writes |
| `copilot/llm.py` | OpenRouter client with model fallback and response cache |
| `copilot/render.py` + `app.py` | Streamlit generative UI: status card, table, line chart, bar chart, map, heatmap, evidence and conflicts |

## License

[MIT](LICENSE)
