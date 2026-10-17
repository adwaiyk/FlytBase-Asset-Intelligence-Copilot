# WellWise: Asset Intelligence Copilot
**FlytBase challenge · Hacktoberfest Hack Day Pune · 17 Oct 2026** · Repo: github.com/adwaiyk/FlytBase-Asset-Intelligence-Copilot (MIT) · Model: Gemma 4 31B (open weights) via OpenRouter · UI: Streamlit

## Page 1: System design

**Thesis.** Code computes and Gemma reasons. Every number comes from deterministic, tested tools over the records. The rules come from the manuals and SOPs. Gemma 4 plans the tool calls, picks the visual and writes the cited answer.

**Data: stored, indexed, retrieved.** One loader reads any number of dataset folders by glob into pandas DataFrames (600 wells, 125k inspections, 17k repairs, 4.4k reports and 1.9k notes, loaded in about 10 s). DuckDB serves read-only SQL over curated views. "Today" is auto-detected as the last inspection date plus one day. On ingest, each repair report is parsed into structured fields: containment hours, compliance-table rows, stated spill class, parts installed (serial and lot) and follow-ups. The manuals and SOPs are chunked by section and by protocol row (SR-01, OPS-2, …) into a BM25 index.

**Rules registry.** Thresholds and deadlines are extracted from the documents: producing Δ°C, RCA count, spill classes, SR-01/02/03, RC-04, OPS-1 deadlines, MOC well lists and expiries, and recall lots. Each comes with its section quote, and well types inherit from each other (T350/T500 → T200). The test set's new **T500** threshold (25 °C) was picked up with no code change.

**Effective view.** Raw records are overlaid with corrections (dataset `correction` / `data_correction` notes plus corrections users give in chat), with the originals kept. Each well's type history is respected and plugged wells are excluded. Every tool reads this view, so a correction changes every later answer for every user.

**Tools (26).** Domain tools: `well_snapshot`, `fleet_status`, `timeseries`, `downtime`, `spills`, `compliance_audit`, `repairs`, `rca_candidates`. Procedure audits: OPS-1 gas response, OPS-2 bypass vs MOC, OPS-3 status precedence, OPS-5 freeze check, OPS-4/6 failure classes, recall, regulator-letter follow-up, shut-in delay reasons. Documents: `search_docs`, `read_document`. Memory: `record_feedback`, `recall_my_conversations`, `save_my_preference`. Fallback: `run_sql`. Every tool returns a compact summary for Gemma plus full rows and sources for the UI.

**Numbers + documents + notes.** Example: "Which rules has WELL-0001 broken?" joins the spill inspection, regulator events, the containment time found only in the repair report, and the SOP deadlines, then separates breaches (deadline passed) from pending items.

**Memory.**

- *Shared:* every fact or correction a user gives becomes an **assertion** (kind, scope, author, time, validity, original value, status) that all users see.
- *Private:* each user's conversations, episodic memory ("the wells we discussed yesterday") and preferences are filtered by `user_id` in SQL. The model never sees anyone else's.
- *Feedback scope:* each correction or rule applies only where it was stated, e.g. one inspection, one well, or one well type.

**Conflicts.** Every write is checked against the latest inspection, inspector remarks and other people's claims. It ends up *applied*, *unconfirmed* (it contradicts the data, or is second-hand) or *disputed*, and the answer shows both sides with sources. Missing data (e.g. reservoir pressure) is stated, never invented.

**Generative UI.** Gemma names a component and a result handle, and the server binds the real rows. A user-named visual always wins. Components: status card, table, line chart (not-producing points marked), bar and stacked bar, map and heatmap, each with evidence and the tool trace.

**Auth.** Per-user login with PBKDF2-SHA256 passwords, server-side sessions, and lockout after 5 failed attempts.

**Models and cost.** Gemma 4 31B, falling back to Gemma 4 26B-A4B, on OpenRouter's free tier. A question takes about 3–6 model calls, and responses are cached. **Model cost: USD 0.**

**Verification.** 12 automated tests cover the expected example answers (Q1–Q11, Q14 exact), feedback scopes, privacy and lockout, and the procedure audits on the test set.

**Next.** Bitemporal store, role-based permissions for corrections, proactive alerts (overdue reports, recalled pumps), EmbeddingGemma hybrid search, and Gemma vision for drone imagery.

## Page 2: Results on the final questions (test set, 600 wells, today = 15 Jan 2027)

| # | Question | Copilot result (verified against the records) |
|---|---|---|
| Q1 | Reservoir pressure map | **Cannot be answered from the data.** No pressure field exists in any inspection or record; flowline test pressures are not reservoir pressure. Says so and offers what is measured. |
| Q2 | Most oil produced in 2026 | **Volumes are not recorded.** Proxy: weeks producing. Several wells tie at 53/53 producing weeks (e.g. WELL-0051, 0530, 0536, 0586, 0594), so there is no single "best producer" from the data. |
| Q3 | Gas reports since 1 Nov 2026 (OPS-1) | **26 reports: 17 met, 9 missed.** Deadline 24 h, or 12 h from 1 Jan 2027. Response = repair start or manual inspection; drones don't count. E.g. WELL-0163 missed (251 h), WELL-0332 had no response. |
| Q4 | Temporary bypasses (OPS-2 + MOC) | **In place now:** WELL-0248 *Allowed* (MOC-2026-031, extended by MOC-2026-044 to 28 Feb 2027), WELL-0249 *Expired* (MOC-036, 15 Dec 2026), WELL-0405 *Not approved*. **Past violations:** WELL-0561 not approved; WELL-0158 and WELL-0087 stayed in past 15 Dec. |
| Q5 | Regulator letter (NE-07/NE-08 reportable spills since 1 Jun 2026) | **6 spills covered, 3 non-compliant:** WELL-0123 (MNT-0123-014), WELL-0182 (MNT-0182-028), WELL-0262 (MNT-0262-029) lack "Soil samples sent to the lab." Compliant: WELL-0168, 0277, 0119. |
| Q6 | Inspection vs operator note disagree (OPS-3) | **15 wells**, resolved by recency. E.g. WELL-0026/0032/0033/0046 *producing (unconfirmed)*: a restart note is newer than the inspection. WELL-0044/0323 *not producing (shut in)*. WELL-0010 not producing: it is T350 since Nov 2026 (20 °C rule). |
| Q7 | Wells that "sound wrong", ranked | Built from operator notes (rattling, fluid pound, tagging bottom, amps hunting, drive tripping) with no repair since, plus warning signs from the data. Ranked by the model with the notes quoted; judgement question. |
| Q8 | Who told you that? | Nathan's WELL-0333 swap is recorded as shared, *no work order yet*. His sort/units preference stays private. Olivia's "Nathan told me…" on WELL-0577 is *unconfirmed, second-hand*. The recall list keeps both wells and shows where each claim came from. |
| Q9 | Multi-topic session | 9 recalled pumps are still in the ground per the records (NE-08 2, NW-12 4, SE-32 1, SW-23 2). Northwest Production is led by **Nathan Pierce**, with **150 wells**. Cold weather (OPS-5): ≤ −5 °C on a producing well needs a heat trace check within 7 days; missed in December at e.g. **WELL-0310** (also 0354, 0486, 0531). WELL-0332 on 3 Dec: **no H2S reading is recorded** (no response visit; OPS-1 missed). Not producing among the recall wells: **WELL-0160, WELL-0263**. |
| Q10 | What are we waiting on (2026) | **251 delayed jobs:** parts 117, contractors 76, crews 58 (median ~9 extra days each). **Southeast Block 31 stands out**: crew delays have a 20-day median. Weather appears only in notes (26), never as a report's cause. Shown as a stacked bar chart. |
| Q11 | Region that runs hotter | **Southeast Block 31**: wellheads average 31.5 °C above air vs 26–29 °C elsewhere (2026+). Ambient air is ~21 °C in every area, so this is the wells, not the climate (judgement; partly well-type mix). |

**What worked.** Rules read from documents carried over to new well types, MOC extensions, recall lots and the new 12-hour deadline without retuning. Corrections and second-hand claims flowed into later answers with attribution. Missing data was declared rather than invented.

**What didn't, and why.** OpenRouter was blocked from our cloud build environment, so we could not produce full live Gemma transcripts for every turn there. The results above come from the same deterministic tools Gemma calls, each verified against the records. Q7 ranking and Q2/Q11 are judgement calls, so the answers explain the proxy used. The free-tier rate limit (50 requests/day) is the main operational risk, which caching mitigates.
