# WellWise · FlytBase Asset Intelligence Copilot

A chat copilot that answers operators' plain-English questions about an oil field, **correctly and with evidence**, built for the FlytBase challenge at Hacktoberfest Hack Day Pune (17 Oct 2026). Powered by **Gemma 4** (open-weight) through OpenRouter.

**Design:** Gemma 4 plans, calls tools, picks the visual and writes the answer; a deterministic semantic layer computes every number over the data *with corrections applied*, and rules (thresholds, deadlines) are read from the manuals and SOPs at load time. Full design: [`docs/SYSTEM_DESIGN.md`](docs/SYSTEM_DESIGN.md).

```
Next.js 15 + shadcn/ui (web/)  ──BFF, httpOnly cookie──▶  FastAPI (copilot/server.py)
  login · private chats · generative UI                    auth · agent harness · Gemma 4 via OpenRouter
  status card · table · line · bar · map · heatmap          semantic layer (pandas + DuckDB) · SQLite memory
```

## Run it

```bash
# 1. Python API (from the repo root)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                       # put your OPENROUTER_API_KEY in .env
python -m copilot.cli info                 # what was loaded: wells, areas, rules from manuals, "today"
uvicorn copilot.server:app --port 8000

# 2. Web app (second terminal)
cd web && npm install && npm run build && npm start      # http://localhost:3000
```

Sign in as any person in `fleet/users.json`; the first-start password is `COPILOT_DEFAULT_PASSWORD` in `.env` (default `flytbase2026`). Change it from the user menu.

The dataset is included in `data/flytbase-dataset/` (MIT, from [FlytBaseAILabs/flytbase-ahc-swe-asset-intelligence-dataset](https://github.com/FlytBaseAILabs/flytbase-ahc-swe-asset-intelligence-dataset)). By default the app loads `test-data/dataset` (600 wells, today = 15 Jan 2027), which is a superset of the sample. To use the sample only: `COPILOT_DATA_DIRS=data/flytbase-dataset/sample-data`.

## Run the question sets

```bash
python -m copilot.cli run eval/final.json    --out results-final.md    --db /tmp/final.db     # the 11 final questions (21 turns, multi-user)
COPILOT_DATA_DIRS=data/flytbase-dataset/sample-data \
python -m copilot.cli run eval/examples.json --out results-examples.md --db /tmp/examples.db  # the 18 example questions
python -m pytest -q tests                                                                    # engine vs expected answers, auth, privacy (no model needed)
```

## Security

- Passwords: PBKDF2-SHA256, 200,000 rounds, per-user salt; constant-time comparison.
- Sessions: random 256-bit tokens, stored server-side with expiry, revoked on sign-out; a password change signs out every other session.
- The browser never sees the token: the Next.js server keeps it in an `httpOnly`, `SameSite=Strict` cookie (`Secure` over HTTPS) and attaches it server-side (backend-for-frontend). Only an allow-list of API paths is proxied.
- Sign-in is rate-limited: 5 failures lock the account for 15 minutes, with an IP-wide cap; a locked account rejects even the right password.
- CSRF: SameSite=Strict plus an Origin check on every state-changing request. Security headers: CSP, `X-Frame-Options: DENY`, `nosniff`, strict referrer policy.
- Privacy: conversations, episodic memory and preferences are filtered by the signed-in user in SQL; corrections and well facts are shared with the team by design.

## What's inside

| Path | Role |
|---|---|
| `copilot/data.py` | Ingestion of any number of dataset folders; repair-report parser (containment time, compliance table, parts installed, follow-up); **rules registry extracted from the manuals/SOPs** with inheritance (T350/T500 → T200); BM25 document index |
| `copilot/engine.py` | Semantic layer over an effective view (raw ⊕ corrections, originals kept; type history; plugged wells): `well_snapshot`, `fleet_status`, `timeseries`, `downtime`, `spills`, `compliance_audit`, `repairs`, `rca_candidates`, `well_notes`, `search_docs`, `read_document`, `get_rules`, `run_sql` |
| `copilot/feedback.py` | Write path: corrections to raw data and AI analysis, scoped rules, shared well facts; resolves the record in code; conflict engine (applied / unconfirmed / disputed) |
| `copilot/store.py` | SQLite: accounts, sessions, login attempts, private conversations, episodic memory, private preferences, shared assertions |
| `copilot/agent.py` · `copilot/llm.py` | Agent harness (context assembly, tool loop, visual policy, grounding check) · OpenRouter client with model fallback and response cache |
| `copilot/server.py` | FastAPI: auth, conversations, chat, field overview |
| `web/` | Next.js 15 + shadcn/ui (Radix + Tailwind v4): login, private chat history, KPI strip, generative UI components, evidence and tool trace |

## License

[MIT](LICENSE)
