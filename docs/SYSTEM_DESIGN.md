# WellWise: Asset Intelligence Copilot, System Design & Battle Plan

> Hacktoberfest Hack Day Pune × AI Hackers Collective · FlytBase challenge · 17 Oct 2026
> Targets: **(1) Asset Intelligence Copilot Challenge**, **(2) Best Use of Gemma 4**, **(3) Best Open-Source AI Project**

---

## 0. TL;DR: the 10 decisions

1. **Numbers come from code; the LLM never does the arithmetic.** A deterministic *semantic layer* of domain tools computes producing status, downtime, spills, compliance and costs. `scripts/golden_check.py` already reproduces the expected answers for Q1–Q11 and Q14 exactly with plain pandas. The LLM (Gemma 4) plans, calls tools, picks the visual and writes the answer.
2. **Rules come from the manuals at ingest time, never hard-coded.** A *rules registry* (thresholds, deadlines, RCA counts, spill classes) is extracted from `fleet/**/*.md` with Gemma plus a regex cross-check. It stores the verbatim quote and section for citations, and it supports inheritance (T350 → T200). A new `T500.md` in the test dataset is then picked up automatically.
3. **One abstraction holds all human knowledge: the Assertion.** Dataset notes (`context.jsonl`) and everything users tell the copilot (corrections, AI-analysis fixes, scoped rules, shared facts, claims) are rows in one append-only store, with author, scope, validity, status and the original value kept.
4. **The effective view is raw data plus applied assertions.** Every tool reads from views where corrections are overlaid, with the original values and provenance kept. A correction therefore changes every later answer, for every user, at its scope only.
5. **A conflict engine runs on every write.** A new assertion is checked against sensor evidence, inspector observations and other people's assertions. It ends up `applied`, `unconfirmed` or `disputed`, and the answer always shows the conflict.
6. **Privacy is enforced in SQL, not in the prompt.** Private conversational memory is keyed by `user_id` in the query layer, so the LLM cannot even see another user's history.
7. **Generative UI uses a declarative component catalog (A2UI-style) with data binding by handle.** The LLM emits `{component, result_id, field mapping}` and the server binds the real rows, so numbers never pass through the LLM by hand. There are 6 required components plus citation chips and a conflict banner.
8. **Every answer carries evidence.** Tools return `source` refs (record ID, file, report section, manual §). A post-answer **grounding check** verifies that every number and ID in the text appears in tool outputs.
9. **The eval harness doubles as the results generator.** The 18 examples are encoded as scripted multi-user scenarios. In the final 2 hours the same runner executes the final questions and writes `results.md` for write-up page 2.
10. **Stack:** Python · DuckDB (JSONL via glob) · SQLite (memory) · rank-bm25 · google-genai (Gemma 4 31B / 26B-A4B) with an Ollama fallback · Streamlit + Plotly · MIT licence · Agent Skill + MCP server for the open-source prize.

---

## 1. What the judges actually score (read this twice)

| Source | What it says | Design consequence |
|---|---|---|
| Problem statement | "Engineer the **agentic AI layer in the middle**: storage/retrieval, tools, numbers + documents, memory" | Architecture is the product. Write-up page 1 must explain each of these. |
| Judging | Results checked against expected answers; **"A sound, general design that answers 12 reliably beats a fragile one that gets 20 by luck."** | Deterministic tools + generic fallback. No per-question hacks. |
| Answer checks | **Facts** (numbers, names, IDs, dates match) · **Evidence** (cites records + docs) · **Visual** (asked-for, or fitting) | Answer contract has all three, validated before display. |
| Naming | Wells by ID; areas/teams/people **by name** | Always map `U-201` → "Michael Turner", `NE-07` → "Northeast Block 7". |
| Robustness | "A system tuned to the sample questions will break"; test dataset has **more wells & more history**, loaded **alongside** sample | Glob ingestion of N data dirs, rules from manuals, auto-detected as-of date. |
| Submission | 2 pages (repo says 2–3, keep to 2) + ≤5-min video in your own voice + **public repo with OSS licence** | Repo public + LICENSE now. Write-up drafted before 16:00. |
| Showdown | Shortlisted people walk through the design | Both teammates must be able to explain every box in §3. |

**Date gotcha:** the PDF says "today" = 17 Oct 2026, but the repo (newer) says **16 Oct 2026**, and Q6's window "16 Jun–16 Oct" confirms 16 Oct. Make `AS_OF` configurable and auto-detect it as `date(max(inspected_at)) + 1 day` (sample: 15 Oct → 16 Oct). Re-check when the test dataset drops.

---

## 2. Domain rules the engine must encode (all verified against the expected answers)

| Concept | Rule | Source to cite |
|---|---|---|
| Producing | `wellhead_temp_c − ambient_temp_c ≥ threshold(well_type)`; T200 = 15 °C, T350 = 20 °C. Absolute temperature is irrelevant (51.6 °C can be "not producing"). | T200 §9.3, T350 §3 |
| Right now | Each well's **latest inspection** | Eval doc |
| Downtime | `7 days × #inspections not producing` in the window. Missed inspections add 0. **Never** use `maintenance.downtime_hours`. | Dataset guide |
| Periods | "last 4 months" = calendar months back from today (16 Jun–16 Oct); "last 90 days" = today − 90 d; "in 2025"/"this year" = calendar year; a **repair belongs to a period by `started_at`** | Eval doc |
| Real spill | `spill_detected` and **no formal `correction` note** on that `inspection_id`. `operator_feedback` notes that only mention an inspection in their text (e.g. "Inspection INS-0101-0197: …") are **not** corrections: show the disagreement, the detection stands. | Spill SOP §7, Q4, Q18 |
| Spill class | minor < 1 bbl · moderate 1–<5 · **reportable 5–<25** · major ≥ 25 (uses the *effective* volume after corrections) | Spill SOP §3 |
| SR-01 | Reportable: written notice ≤ 24 h from the inspection time (major: 2 h). `hours_to_report` on `spill_report_filed`. | Spill SOP §4 |
| SR-02 | Contained ≤ 4 h. **Only in report text** ("contained about 7.1 hours") | Spill SOP §4 + reports |
| SR-03 | Reportable/major: agency verification within 60 days of discovery, closed only by a passing site inspection | Spill SOP §4 |
| HSE notice | Moderate spills: HSE notified within 72 h (in report compliance table) | Spill SOP §3 |
| RC-01..05 | Inspect every ≤ 14 d · annual flowline integrity test (`issue = "Annual flowline integrity test"`) · down > 14 consecutive days → report to supervisor · NOV answered in 30 d (`nov_response_filed`) · flowline maintenance programme | Reg. Compliance SOP |
| RCA | ≥ 3 **corrective** events on the same `equipment_kind` in the 12 months before today; T350 inherits from T200 | T200 §10, T350 §6 |
| Breach vs pending | Breach only if the deadline has passed (as of today) and the requirement is unmet; otherwise it is **pending/open** (Q9, Q13) | Eval Q9 |
| "Why is it down?" | (1) an active human note/assertion whose validity covers the date → (2) an open repair (`completed_at > today`) → (3) the corrective repair triggered by that inspection → else **"No recorded reason"**, quote the inspector's remark as an *observation* and suggest a check. **Never invent a cause.** | Q1, Q2 |
| Recorded status | Out of date if it disagrees with the computed status, so say so explicitly | Dataset guide |
| Context ≠ rule | Notes like "expect ~3 °C lower wellhead temp" are context, **not** threshold changes. Only an explicit scoped rule from a user changes a rule. | Q3 expected output |

Data facts: 200 wells, 4 areas (SW-23, SW-24, NE-07, NE-08), 39,567 inspections (drone 33,737 / manual 5,830), 5,665 repairs, 1,509 reports, 90 regulator events, 141 notes (82 operator_note, 56 correction, 3 operator_feedback), 15 users. `report_file` names vary, so always follow the field (e.g. `MNT-0001-june-2026-flowline-spill.md` is MNT-0001-029). 9 reports are still in progress ("Work done so far").

---

## 3. Architecture

```
                    ┌──────────────────────────── Streamlit UI ─────────────────────────────┐
                    │ user picker · chat list · "session date" (sim clock) · reset memory    │
                    │ GenUI renderer: StatusCard | Table | Line | Bar | Map | Heatmap        │
                    │ + CitationChips (expand → raw record, original vs corrected)          │
                    │ + ConflictBanner · MemoryWriteReceipt · "Field briefing" panel        │
                    └───────────────▲─────────────────────────────┬─────────────────────────┘
                     answer contract│(text + visual spec + evidence + conflicts)
                    ┌───────────────┴─────────────────────────────▼─────────────────────────┐
                    │                    AGENT HARNESS (our own, ~300 LOC)                   │
                    │ 1 Context assembly: role, as-of, entity linking (regex WELL-/INS-/MNT-,│
                    │   area & people names) → inject shared assertions + private memory     │
                    │ 2 Intent router (Gemma 4 26B-A4B, JSON): ask | correct_raw | correct_ai│
                    │   | scoped_rule | shared_fact | status_claim | recall                  │
                    │ 3 Write path: extract → resolve target in code → conflict engine →     │
                    │   persist assertion → re-run read path to show consequences           │
                    │ 4 Read path: tool loop (Gemma 4 31B, native function calling, ≤6 steps)│
                    │ 5 Visual policy (user-named visual wins) → bind result_id → validate   │
                    │ 6 Grounding check: numbers/IDs ⊂ tool outputs, else 1 repair round    │
                    └───────▲──────────────────────▲──────────────────────────▲─────────────┘
                            │ domain tools          │ doc tools                │ memory tools
        ┌───────────────────┴──────┐  ┌─────────────┴────────────┐  ┌──────────┴─────────────┐
        │ SEMANTIC LAYER (DuckDB)  │  │ KNOWLEDGE (BM25 [+Emb.]) │  │ MEMORY (SQLite)        │
        │ v_wells, v_inspections_  │  │ manual/SOP sections,     │  │ assertions (shared,    │
        │ eff (producing, delta),  │  │ protocol rows, report    │  │ scoped, provenance)    │
        │ v_spills_eff (class),    │  │ chunks                   │  │ conversations/messages │
        │ v_repairs, v_reports,    │  │ RULES REGISTRY: key,     │  │ episodic memory        │
        │ v_reg_events, v_notes    │  │ scope, value, quote, §,  │  │ (user_id-scoped:       │
        │ (raw ⊕ applied overlay)  │  │ inherits_from            │  │  entities, result sets)│
        └───────────▲──────────────┘  └─────────────▲────────────┘  └───────────▲────────────┘
                    │ INGEST (one command, idempotent, N data dirs, < 1 min)      │
        assets/*/*.jsonl, metadata.json ─ read_json_auto(glob) │ reports/*.md → parser (regex
        + markdown-table) → report_facts; Gemma fallback on parse miss │ fleet/*.md → sections +
        rules extraction (Gemma JSON + regex verify) │ context.jsonl → assertions(source=dataset)
```

### 3.1 Storage & indexing

| Store | Contents | Why |
|---|---|---|
| **DuckDB (in-process)** | Raw facts loaded with `read_json_auto('…/assets/*/inspections.jsonl', filename=true)` over **every data dir** (sample + test) with `UNION BY NAME`; dedupe on natural keys; `dataset` column | 40K rows load in about a second. Real SQL for the generic fallback tool. Globs make "load alongside" trivial. |
| **Effective views** | `v_inspections_eff`: raw columns, `effective_*` columns from applied assertions, `delta_c`, `threshold_c`, `producing`, `correction_ids`, `original_*` | One place where corrections take effect, so every tool inherits them |
| **report_facts** | Per report: `maintenance_id` (from header), `containment_hours`, `spill_class_stated`, `hse_notice_hours`, `report_written`, `in_progress`, compliance rows `(protocol, result, detail)`, root cause, recommendations, `action_required` | "Some facts live only in the reports", now queryable. The parser covers 100 % of the sample, with a Gemma fallback for unseen phrasing. |
| **rules registry** | `(rule_key, scope{well_type}, value, unit, doc, section, quote, inherits_from, source=manual\|user, author)` | Thresholds and deadlines live in the docs; user overrides (Q14) live here too, with a scope |
| **Doc index** | Manual/SOP split by heading and by protocol-table row (SR-01 is its own chunk); reports split by section; BM25 (rank-bm25). Stretch: EmbeddingGemma hybrid | Small corpus. BM25 is exact on IDs like "SR-02". |
| **SQLite memory.db** | `assertions`, `conversations`, `messages`, `episodes` | Mutable, multi-process safe (WAL), snapshot/restore for eval resets |

Registering small SQLite overlay tables into DuckDB per request (`con.register`) keeps both worlds simple.

### 3.2 Tool catalog (small, high-level, typed with pydantic)

Every tool returns `{result_id, summary (compact, for the LLM), rows (full, kept server-side), sources[], suggested_visual}`. This is the context-engineering piece: the LLM sees aggregates plus the top rows, the UI gets everything by handle.

| Tool | Covers | Notes |
|---|---|---|
| `resolve_entities(text)` | names → IDs | areas, users, wells, inspections by date ("15 Oct reading for WELL-0164" → INS-0164-0205) |
| `well_snapshot(asset_id)` | Q1, Q15, Q17 | latest inspection, effective delta vs threshold, producing, reason chain, recorded-status staleness, active shared assertions, open repairs, conflicts |
| `fleet_status(area?, well_type?, producing?)` | Q2 | one row per well "right now" with reason chain |
| `timeseries(asset_id, metrics, period)` | Q3 | weekly wellhead/ambient/delta + producing flag for markers |
| `downtime(scope, period, top_n?, group_by?)` | Q5, Q6 | evidence = the non-producing inspection IDs, ties made explicit, "next is …" |
| `spills(scope, period, real_only=True, min_class?, group_by?)` | Q4, Q7, Q8, Q15 | effective volume, class, corrected-out detections listed separately, lat/lon |
| `compliance_audit(scope, period)` | Q9, Q10, Q13, Q15 | joins spill → reg events → report facts → SOP rules → breach / pending / met with deadlines and citations; flags stale report conclusions after corrections |
| `repairs(scope, period, type?, equipment_kind?, agg?)` | Q11 | costs by `started_at` |
| `rca_candidates(scope, equipment_kind?)` | Q14 | applies the scoped rule resolution and says which rule (manual vs user) applied |
| `get_rule(rule_key, well_type)` / `search_docs(query, k)` | any "why/what does the SOP say" | returns verbatim quotes and § |
| `well_notes(asset_id, period?)` | context and disagreements | dataset notes + runtime assertions, with authors by name |
| `recall_my_conversations(when?, about?)` | Q11, Q16 | **user_id injected by the harness, not an LLM argument**; "yesterday" = sim date − 1, otherwise falls back to the latest earlier session and says so |
| `record_assertion(...)` | write path | called by the router, not freely by the read agent |
| `run_sql(query)` | **unseen questions** | read-only, `SELECT` only, curated views, LIMIT + timeout, schema doc in prompt; IDs in results are auto-cited |

### 3.3 Memory at two levels + learning from feedback

**Assertion schema**

```
id, kind: correction_raw | correction_ai | scoped_rule | shared_fact | status_claim | dataset_note
scope:   {asset_id?, inspection_id?, well_type?, area_id?, equipment_kind?}
target:  {table, record_id, field}        old_value, new_value, unit
text, rationale, author_user_id, created_at, valid_from, valid_to
visibility: shared | private              source: dataset | chat (session_id, message_id)
status: applied | unconfirmed | disputed | superseded      conflicts: [assertion/record refs]
```

| Requirement | Mechanism | Example check |
|---|---|---|
| Shared knowledge about a well | `shared_fact` assertions (visibility=shared) are auto-injected into `well_snapshot` and the reason chain for **any** user while valid | Q16: Jake's WELL-0007 workover → Michael sees "planned from 17 Oct, ~10 days, per Jake Morales" |
| Private per-user memory | `episodes` row per answered turn: `(user_id, session_id, sim_date, question, answer_summary, entities[], result_id)`; retrieval filtered by `user_id` in SQL | Q11 works for Michael; Q16 Jessica gets "no earlier conversation" |
| Raw-data correction | `correction_raw` on `(inspection, wellhead_temp_c)`; original kept; effective view switches; conflict check against the inspector's note | Q12 → WELL-0164 producing; "Pump jack not moving" (Tyler Hughes) flagged, ask to confirm; Q2 rerun shows 3 wells and says why |
| AI-analysis correction | `correction_ai` on `(inspection, spill_est_volume_bbl)`; class recomputed; compliance re-audited; report conclusions marked superseded | Q13 → reportable, SR-01 possible breach, SR-03 due 23 Nov 2026, MNT-0151-025 "moderate" no longer holds |
| Scoped rule | `scoped_rule` on `(rca_threshold, well_type=T350, equipment_kind=pump_jack)`; resolution order asset > area > well_type > manual | Q14 → adds WELL-0120 (T350) and **not** WELL-0102 (T200); answer says "per Michael Turner's rule, not the manual" |

### 3.4 Conflict policy (honesty)

| Situation | Status | Answer behaviour |
|---|---|---|
| User supplies a **new measurement** replacing a recorded value | `applied` | Use it everywhere. If other evidence disagrees (inspector remark), show a ConflictBanner and ask the author to confirm. |
| User **claims a state** that matches the evidence | `applied` (shared_fact) | Record it, and use it as the reason in later answers (Q17, Michael's shut-in note) |
| User **claims a state** that contradicts the latest inspection | `unconfirmed` | Say the data disagrees (cite inspection, delta, threshold), name who agrees, keep both, ask for confirmation (Q17 Tyler, Jake) |
| Two humans disagree, no formal correction | `disputed` | The answer follows the record ("detection stands") and shows both sources (Q18) |
| Formal `correction` note in the data | `applied` | The detection is removed from counts and listed as "corrected, not counted" (Q4) |
| Later correction on the same target | older one `superseded` | Show the history in the citation drill-down |

### 3.5 Generative UI contract

```json
{
  "answer": "**No, WELL-0001 is not producing oil.** ...",
  "visual": {"component": "status_card|table|line_chart|bar_chart|map|heatmap",
             "result_id": "r2", "x": "asset_id", "y": "downtime_days",
             "series": ["wellhead_temp_c","ambient_temp_c"], "markers": {"field":"producing","when":false},
             "lat": "lat", "lon": "lon", "rows": "area_name", "cols": "month", "value": "spills",
             "title": "Top 3 downtime, Northeast Block 7 (16 Jun–16 Oct 2026)"},
  "evidence": [{"kind":"inspection","id":"INS-0001-0203"},{"kind":"doc","doc":"T200.md","section":"9.3"}],
  "conflicts": [{"kind":"disputed","sources":["CTX-0101-002","CTX-0101-003"]}],
  "memory_writes": [{"id":"A-17","kind":"correction_raw","status":"applied"}]
}
```

- **Visual policy, enforced in code:** if the user names a visual (regex: table, map, heatmap, bar, line, chart, card), it wins. Otherwise the LLM chooses, using the guide's mapping: one well now → status card · list → table · over time → line · compare a few → bar · where → map · 2-D → heatmap. A short factual answer may have no visual (Q5).
- The renderer validates the spec with pydantic. If validation fails, it falls back to a table of that result (no crash, no blank).
- Plotly: line with red markers where `producing=false`; horizontal bar; `px.imshow` heatmap with totals; `scatter_map` on OpenStreetMap tiles (no API key); status card = a styled container with a big ✅/⛔, delta vs threshold, recorded status (badge "out of date"), reason, last inspection, inspector by name.
- Citation chips under every answer: click to expand the raw JSON record or the manual quote; corrected fields show `original → corrected (by, when, why)`.

### 3.6 Agent harness prompts (keep short; Gemma 4 does better with crisp rules)

System prompt = role + today + current user (name, role, team) + 15 golden rules (§2 condensed) + tool usage policy ("never compute numbers yourself; never invent a cause; cite IDs; refer to people/areas by name; surface conflicts") + answer-contract schema. Few-shot: 2 compact examples (one list question, one correction). Max 6 tool steps. If a tool fails, retry once with fixed arguments, then fall back to `run_sql`.

### 3.7 Models & cost

| Job | Model | Why |
|---|---|---|
| Agent reasoning + answer | **Gemma 4 31B IT** (Google AI Studio / Gemini API, `gemma-4-31b-it`) | Strongest open model available; native function calling |
| Router, write-path extraction, ingest extraction (rules, report fallback) | **Gemma 4 26B A4B IT** (`gemma-4-26b-a4b-it`) | MoE, fast, cheap |
| Fallback when rate-limited | Ollama `gemma4:12b`/`26b` (OpenAI-compatible endpoint) → OpenRouter `google/gemma-4-31b-it:free` | Same adapter; OpenRouter free = 50 req/day only |
| Stretch: photo → correction | Gemma 4 multimodal | User uploads a photo of the thermal-gun display or field sheet → value extracted → `correction_raw` with the image as evidence |
| Stretch: embeddings | EmbeddingGemma via Ollama | Hybrid search over reports |

Budget: about 3–5 LLM calls per question, about 30–50K tokens. **Cost: USD 0** (free tier). Cache LLM responses by prompt hash so eval reruns cost no quota. **Check Gemma rate limits in AI Studio now**, because they are not published.

---

## 4. Ingestion pipeline (`python -m copilot.ingest --data sample-data [--data test-data]`)

1. Fleet: merge `areas.json`/`users.json` from all dirs (union by ID).
2. Assets: DuckDB glob reads → tables → dedupe by `inspection_id` / `maintenance_id` / `event_id` / `note_id`.
3. Reports: follow `report_file`. Parse the header (MNT id, dates, crew), the containment regex `[Cc]ontained (about )?([\d.]+) hours`, the compliance markdown table, `Report written`, `Work done so far` (in progress). Any miss goes to the Gemma JSON extraction fallback, with the parse-failure count printed.
4. Manuals/SOPs: chunk them, then run rules extraction with the JSON schema. Validate that each `quote` is a verbatim substring and the number appears in it. Detect inheritance ("follow the T200 manual", "Same as T200"). Print the rules table for a human eyeball check.
5. Notes → assertions (`source=dataset`). Link the free-text inspection IDs in notes via regex (`INS-\d{4}-\d{4}`).
6. Set `AS_OF` = max inspection date + 1 day (overridable), then print a **sanity report**: wells/area, well types + thresholds, date range, counts, report parse coverage, notes linked.

Robustness test before 16:00: create a fake `T500.md` (threshold 25 °C) plus 2 fake wells in a new area, and ingest them alongside the sample. The copilot must answer about them with no code change.

---

## 5. Evaluation harness = results generator

`eval/scenarios.yaml`: each scenario is a list of turns `{user, new_chat, sim_date, text, expect: {facts: [...], ids: [...], visual: "bar_chart"}}`, with `reset: true` (snapshot/restore `memory.db`; "run each scenario on the original sample data unless it says it follows another one").

`python -m copilot.eval eval/scenarios.yaml --out results.md` → per turn: answer, visual type, evidence, pass/fail per expected fact, latency. Encode all 18 examples **first**, then use the runner as the regression gate. At 16:00, write the final questions in the same format and run them; the output is the draft of write-up page 2.

---

## 6. Prize strategy (one build, three prizes)

| Prize | What wins it | Concrete items |
|---|---|---|
| **Asset Intelligence Copilot** | Correct facts + evidence + right visual on the final questions; sound general design; clear 2-pager & video | §2–§5; deterministic semantic layer; assertion overlay; conflict engine; eval runner |
| **Best Use of Gemma 4** | Gemma is the brain, not a garnish: open model doing tool use, extraction and multimodal | Gemma 4 31B agent + 26B-A4B router/extractor + rules extraction from manuals; stretch: **photo-to-correction** (multimodal) and EmbeddingGemma. Say "100 % Gemma, USD 0" in the video. |
| **Best Open-Source AI Project** | Open-weight AI central · public repo · OSS licence · original harness · **Agent Skill compliant with the Agent Skill Open Standard** | MIT LICENSE; our own harness (no framework); `skills/oilfield-asset-intelligence/SKILL.md` (frontmatter `name` = dir name, lowercase-hyphen ≤ 64 chars, `description` ≤ 1024 chars, optional `license`/`metadata`; `scripts/` calling `copilot.cli`; `references/domain-rules.md`), validated with `skills-ref validate`; stretch: MCP server (FastMCP) exposing the same tools; deploy on **DigitalOcean App Platform** |

Don't forget: **submit on MLH too** (Submit Project, closes 18:30 IST) and **tick all 3 categories**. Separately, send the organiser OneDrive link (write-up + video + repo) **by 18:00**. Optional: a DEV Challenges write-up (mlh.link/dev-hacktoberfest) for promo credits.

---

## 7. Timeline (now → 18:00 IST) & split for 2 people

| Time (IST) | Person A: data & engine | Person B: agent & UI |
|---|---|---|
| 12:50–13:05 | Repo skeleton, `uv`, DuckDB ingest of sample | API key, test Gemma 4 31B **function calling** + note rate limits; Ollama fallback pull |
| 13:05–14:15 | Effective views, report parser, rules registry (regex first, Gemma extraction second), tools for Q1–Q10 + Q14 with golden asserts (port `scripts/golden_check.py`) | Streamlit shell (user picker, chats, sim date, reset), GenUI renderer for 6 components + chips + banner against **mock** results; LLM adapter; tool loop |
| 14:15–15:15 | Assertion store + effective-view overlay + conflict engine + `recall_my_conversations` + `run_sql` | Router + write path (Q12, Q13, Q14, Q16, Q17); answer contract + visual policy + grounding check; wire real tools |
| 15:15–15:50 | Eval runner + 18 scenarios; fix failures; fake-T500 robustness test | Polish UI; record **architecture part** of the video; draft write-up page 1 |
| 15:50–16:00 | **Freeze**, tag `v1`, make repo public, add LICENSE/README | Agent Skill folder (stretch), field-briefing panel (stretch) |
| ~16:00–17:15 | **Test data**: ingest alongside, read the sanity report, check as-of date & any new well-type rules; run the final questions through the runner | Re-run key final questions live in the UI for screenshots; start page 2 from `results.md` |
| 17:15–17:50 | Write page 2 (what worked, what didn't, why) honestly | Record video: 1.5 min design → 3 min one use case end to end (e.g. Q13 correction → compliance flip → Laura sees it) → 0.5 min results; upload |
| 17:50–18:00 | OneDrive link submitted · MLH submission (3 categories) · repo public with licence | |

**Rule for the final 2 hours:** fix only ingestion/loading bugs. Do not tune to questions, because that is what the judges warn against.

---

## 8. Write-up skeleton (2 pages)

**Page 1 (System design):** a 1-line thesis ("deterministic semantic layer + rules from documents + assertion overlay; Gemma plans, code computes") · architecture diagram · storage/index/retrieval · tool list · how numbers + documents + notes combine (one worked example: Q9) · memory levels + feedback scopes · conflicts · new data (globs, rules extraction, inheritance, as-of detection, fake-T500 test) · models + cost (USD 0, calls/question) · next steps (bitemporal store, role-based permissions for corrections, proactive alerts, EmbeddingGemma, real drone imagery with Gemma vision).

**Page 2 (Results):** a table of final questions × (answer summary, visual, evidence cited, ✓/✗/partial) · what worked · what didn't and why (honest root causes) · eval stats on the 18 examples.

---

## 9. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Gemma rate limits / outage mid-demo | Response cache, Ollama local fallback, OpenRouter backup; deterministic tools still work, and the eval runner can retry |
| Gemma's weaker multi-step tool use | Few, high-level tools; router does write-path extraction with a JSON schema; code resolves IDs; max 6 steps; grounding check |
| Test data has new types/areas/phrasing | Rules from manuals + regex cross-check; report parser with LLM fallback + coverage report; glob ingestion; fake-T500 rehearsal |
| "Yesterday" in a same-day demo | Simulated session date in the UI; fallback "most recent earlier session", stated in the answer |
| Hallucinated causes or numbers | Reason chain computed in code ("No recorded reason" is a valid output); grounding check before display |
| Time overrun | Order: tools → UI → memory → eval → stretch. Stretch items are optional. Freeze at 15:50. |

---

## 10. Repo layout

```
copilot/
  config.py            # AS_OF, data dirs, model ids
  ingest.py            # §4
  engine/              # views.sql, tools.py (semantic layer), rules.py, reports.py, compliance.py
  memory/              # store.py (assertions, episodes), conflicts.py
  agent/               # llm.py (gemma/ollama adapter), harness.py, router.py, prompts.py, grounding.py
  ui/                  # app.py (Streamlit), render.py (GenUI catalog)
  mcp_server.py        # stretch
  cli.py               # `copilot ask --user U-201 "..."`, used by the Agent Skill
eval/scenarios.yaml · eval/final.yaml · results.md
skills/oilfield-asset-intelligence/SKILL.md (+ scripts/, references/)
scripts/golden_check.py
docs/SYSTEM_DESIGN.md · LICENSE (MIT) · README.md
```
