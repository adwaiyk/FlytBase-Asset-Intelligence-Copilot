"""Agent harness: context assembly → Gemma 4 tool loop → visual policy →
grounding check → persist (private history + episodic memory)."""
from __future__ import annotations

import json
import re
import traceback
from datetime import date, timedelta

from . import config, feedback, procedures

PROCEDURES = {"gas_odor_audit", "bypass_audit", "status_disagreements", "recalled_pumps", "spill_followup_audit",
              "freeze_protection_audit", "failure_analysis", "shut_in_delays"}
from .engine import Engine, fmt_date
from .llm import LLM
from .store import clean_json

PERIOD = ("Period: 'last_N_days' | 'last_N_weeks' | 'last_N_months' | 'last_N_years' | 'YYYY' (calendar year) | "
          "'this_year' | 'month:YYYY-MM' | 'all'. Or give start/end as YYYY-MM-DD.")
S = {"type": "string"}
SCOPE = {"area": {"type": "string", "description": "Area name or id, e.g. 'Northeast Block 7'"},
         "asset_ids": {"type": "array", "items": S, "description": "Well ids, e.g. ['WELL-0001']"},
         "well_type": {"type": "string", "description": "e.g. T200"}}
TIME = {"period": {"type": "string", "description": PERIOD}, "start": S, "end": S}


def _fn(name, desc, props, req=()):
    return {"type": "function", "function": {"name": name, "description": desc,
                                             "parameters": {"type": "object", "properties": props, "required": list(req)}}}


TOOLS = [
    _fn("well_snapshot", "Current status of ONE well (latest inspection): producing or not, delta vs threshold, "
        "reason, recorded status staleness, shared notes/feedback, open repairs, conflicts.", {"asset_id": S}, ["asset_id"]),
    _fn("fleet_status", "Status 'right now' of many wells (each well's latest inspection) with the reason for any stop. "
        "Use producing=false for 'which wells are not producing'.", {**SCOPE, "producing": {"type": "boolean"}}),
    _fn("timeseries", "Weekly wellhead vs air temperature for one well with producing flags (for line charts). "
        "'last 13 weeks' → period 'last_13_weeks'.", {"asset_id": S, **TIME}, ["asset_id"]),
    _fn("downtime", "Downtime days per well = 7 × weekly inspections not producing, in a period. For one well also "
        "lists each non-producing inspection with its cause. Use top_n for rankings.",
        {**SCOPE, **TIME, "top_n": {"type": "integer"}}),
    _fn("spills", "Real oil spills (corrected detections excluded, corrections applied) in a period with volume, class, "
        "location and disputes. group_by: 'area_month' (heatmap) | 'well' | 'area' | 'month'.",
        {**SCOPE, **TIME, "min_volume": {"type": "number"}, "group_by": S}),
    _fn("compliance_audit", "Rule breaches and open actions: SR-01 report deadline, SR-02 containment time (from repair "
        "reports), SR-03 clean-up verification, RC-04 NOV response, RC-02 flowline test, RCA due, report conclusions "
        "superseded by corrections. protocol filters e.g. 'SR-02'; status filters 'breach'|'pending'|'met'.",
        {"asset_id": S, "area": SCOPE["area"], **TIME, "protocol": S, "status": S}),
    _fn("repairs", "Repairs (maintenance jobs) and their costs in a period, by start date. 'this year' → 'this_year'.",
        {**SCOPE, **TIME, "maintenance_type": {"type": "string", "enum": ["scheduled", "corrective"]},
         "equipment_kind": S}),
    _fn("rca_candidates", "Wells that need a root-cause analysis (corrective repairs on the same equipment kind in the "
        "last 12 months ≥ threshold from the manual or a user's scoped rule).", {**SCOPE, "equipment_kind": {
            "type": "string", "description": "wellhead|pump_jack|rod_string|downhole_pump|flowline|separator"}}),
    _fn("well_notes", "All human notes, corrections and feedback for one well (who said what, status).", {"asset_id": S},
        ["asset_id"]),
    _fn("search_docs", "Search manuals, SOPs and free-text repair reports. Returns quotes with section.",
        {"query": S, "asset_id": S}, ["query"]),
    _fn("gas_odor_audit", "OPS-1: every operator note reporting gas (gas odor, rotten-egg smell, H2S monitor alarm) and whether a "
        "field response (repair job start or MANUAL inspection) came within the SOP deadline.", {"since": S, "until": S}),
    _fn("bypass_audit", "OPS-2: temporary flowline bypasses from operator notes vs MOC memo approvals (with extensions): "
        "in place now, allowed / expired / not approved.", {}),
    _fn("status_disagreements", "OPS-3: wells whose latest inspection and latest shut-in/restart operator note disagree, "
        "with the real status now by the SOP precedence rule.", {"area": SCOPE["area"]}),
    _fn("recalled_pumps", "Supplier recall: wells whose pump in the ground today (latest 'Parts installed') is from a recalled "
        "lot, with install job, date and cost, producing status, and what people said about swaps.",
        {"area": SCOPE["area"], "team": {"type": "string", "description": "Team name, e.g. Northwest Production"}}),
    _fn("spill_followup_audit", "Spills at or above a volume (default reportable) in given areas since a date whose clean-up "
        "report must contain a required phrase (e.g. a regulator letter's soil-sampling demand).",
        {"areas": S, "since": S, "required_phrase": S, "min_volume": {"type": "number"}}, ["areas", "since", "required_phrase"]),
    _fn("freeze_protection_audit", "OPS-5: cold readings (ambient ≤ -5 °C on producing wells, Dec–Feb) and whether a "
        "'Heat trace check' job started within 7 days.", {"start": S, "end": S}),
    _fn("failure_analysis", "OPS-4/OPS-6: classify corrective jobs by root-cause category and find repeat failures.",
        {"period": {"type": "string", "description": PERIOD}, "area": SCOPE["area"], "equipment_kind": S}),
    _fn("shut_in_delays", "Why wells stayed shut in longer than the repair itself (parts, crews, contractors, weather), "
        "parsed from repair reports, by area with share and typical extra days. Use for 'what are we waiting on'.",
        {"period": {"type": "string", "description": PERIOD}, "area": SCOPE["area"]}),
    _fn("list_documents", "List all manuals, SOPs, memos, notices and letters in fleet/.", {}),
    _fn("read_document", "Read a whole fleet document (manual, SOP, MOC memo, recall notice, regulator letter). "
        "Documents hold the rules, deadlines, approvals and lists that decide many answers.", {"doc": S}, ["doc"]),
    _fn("save_my_preference", "Store a PRIVATE preference of the current user about how answers should look "
        "(sorting, units, format). Only this user sees it.", {"text": S}, ["text"]),
    _fn("get_rules", "The rules registry (thresholds, deadlines) from manuals/SOPs plus users' scoped rules.",
        {"well_type": S}),
    _fn("run_sql", "Read-only DuckDB SQL over curated views, for questions the other tools don't cover. Schema: "
        + Engine.SQL_SCHEMA, {"query": S}, ["query"]),
    _fn("recall_my_conversations", "The CURRENT user's own earlier conversations (private). Use for 'we discussed "
        "yesterday', 'last time', etc.", {"when": {"type": "string", "description": "'yesterday' | 'last' | 'YYYY-MM-DD' | 'any'"},
                                          "about": S}),
    _fn("record_feedback", "Store something the user TELLS you (not a question): a correction, a rule, or a fact about "
        "a well. kind: 'correct_reading' (raw value wrong; field wellhead_temp_c|ambient_temp_c, new_value), "
        "'correct_spill_volume' (AI spill estimate wrong; new_value bbl), 'not_a_spill', 'scoped_rule' (rule_key "
        "rca_corrective_count|producing_delta_c|..., new_value, scope well_type/area/asset_id, equipment_kind), "
        "'well_fact' (state/plan of a well shared with everyone; claimed_state producing|not_producing|shut_in|"
        "planned_downtime|other; valid_from/valid_to YYYY-MM-DD). Identify the inspection by date when no id.",
        {"kind": {"type": "string", "enum": ["correct_reading", "correct_spill_volume", "not_a_spill", "scoped_rule",
                                             "well_fact"]},
         "text": {"type": "string", "description": "The user's statement, verbatim"},
         "asset_id": S, "inspection_id": S, "date": {"type": "string", "description": "YYYY-MM-DD of the inspection"},
         "field": S, "new_value": {"type": "number"}, "rule_key": S, "well_type": S, "area": S,
         "equipment_kind": S, "claimed_state": S, "valid_from": S, "valid_to": S,
         "rationale": {"type": "string", "description": "Why, as the user said it"},
         "second_hand_from": {"type": "string", "description": "If the user relays someone else's claim ('X told me…'), X's name"}},
        ["kind", "text"]),
    _fn("show_visual", "Choose the visual for the answer from a previous tool result. component: status_card | table | "
        "line_chart | bar_chart | map | heatmap.", {"result_id": S, "component": {"type": "string", "enum": [
            "status_card", "table", "line_chart", "bar_chart", "map", "heatmap"]}, "title": S}, ["result_id", "component"]),
]

SYSTEM = """You are WellWise, the Asset Intelligence Copilot for an oil field. You answer operators' plain-English questions about wells correctly and WITH EVIDENCE, using tools.

Today is {today}. "Right now" = each well's latest inspection. Periods like "last 4 months" end today.
You are talking to {user_name} ({user_role}, {user_team}). Earlier in this chat: see the messages.

Rules:
1. NEVER compute numbers yourself; get them from tools and copy them exactly. Never invent a cause: if a tool says "No recorded reason", say so and suggest a field check.
2. Producing oil = wellhead − air ≥ threshold for the well type (from the manual). Downtime = 7 days per non-producing weekly inspection. The tools already apply this and all corrections.
3. If the user TELLS you something (a correction, a measured value, a rule for a type/area, a plan or state of a well, "FYI for everyone"), call record_feedback FIRST, then report what was recorded, what changes, and any conflict. If the claim is unconfirmed or conflicts with the data or with someone else, say so plainly, name who said what, and ask for confirmation. After a scoped_rule, re-run the relevant tool to show the effect when the user asks.
4. If the user refers to earlier conversations ("we discussed yesterday"), call recall_my_conversations. If it returns nothing, say you have no such earlier conversation with this user. Never use anyone else's history.
5. Refer to wells by id (WELL-0001) and to areas, teams and people by NAME. Cite record ids (INS-, MNT-, REG-, CTX-, FB-) and documents (e.g. T200 manual §9.3, SR-01) inline.
6. Visual: if the user names one (table, map, heatmap, bar chart, line chart, status card) call show_visual with it. Otherwise one well right now → status_card; a list → table; change over time → line_chart; comparing a few wells/areas → bar_chart; where things are → map; two dimensions (area × month) → heatmap. A short factual answer may need no visual.
7. When people disagree (notes, feedback, data), show both sides and which one the records support. A formal correction note overrides a detection; an operator's opinion does not.
8. Prefer the specialised tools; use run_sql (DuckDB SQL over every record, including note text and full repair-report text via ILIKE) when none fits. Read the relevant documents (read_document) whenever a rule, deadline, approval, recall or letter matters: the documents decide most answers.
9. Before answering about specific wells, check what people told the copilot (run_sql on the feedback table, or well_snapshot/well_notes) and say where each fact came from: records (ids), documents, or a named person. A second-hand claim ("X told me…") is recorded as unconfirmed.
10. Some questions ask for a judgement or cannot be fully answered from the data. If a quantity is never recorded in the dataset (check the schema and documents), say so plainly; never repurpose a different field that only sounds similar (e.g. a test or equipment pressure is not a reservoir property). Then give the best evidence-based proxy, label it as a proxy, and state its limits.
12. The Operations SOP protocols, MOC approvals, supplier recalls and regulator letters have dedicated audit tools (gas_odor_audit, bypass_audit, status_disagreements, recalled_pumps, spill_followup_audit, freeze_protection_audit, failure_analysis, shut_in_delays). Prefer them, and read the document to confirm parameters (dates, phrases, areas).
13. A well's team comes from the well itself (team_id / team_history), not only from its area. Plugged and abandoned wells are not producing and not 'down'.
11. A user's private preferences (below) apply to every answer for that user only.

Fleet documents: {docs}
Areas: {areas}
Teams: {teams}
{prefs}

Answer format (markdown): first line = the direct answer in bold. Then 2-6 short bullets with the key facts and their evidence ids. Mention conflicts/unconfirmed items explicitly. Do not paste whole tables: the visual shows the rows."""

VISUAL_WORDS = [("heatmap", r"heat ?map"), ("map", r"\bmap\b"), ("bar_chart", r"bar ?(chart|graph)"),
                ("line_chart", r"line ?(chart|graph)"), ("table", r"\btable\b"), ("status_card", r"status card|\bcard\b")]


def requested_visual(text: str) -> str | None:
    for comp, pat in VISUAL_WORDS:
        if re.search(pat, text, re.I):
            return comp
    return None


class Agent:
    def __init__(self, engine: Engine, llm: LLM | None = None):
        self.eng = engine
        self.store = engine.store
        self.llm = llm

    # ------------------------------------------------------------------ private memory
    def recall(self, user, conv, when=None, about=None):
        eps = self.store.episodes(user["user_id"], exclude_conv=conv["conv_id"])
        if not eps:
            return {"summary": f"No earlier conversations with {user['name']} on record.", "rows": [], "sources": []}
        sim = date.fromisoformat(conv["sim_date"]) if conv.get("sim_date") else date.today()
        w = (when or "any").lower()
        pick = eps
        note = ""
        if w == "yesterday":
            y = str(sim - timedelta(days=1))
            pick = [e for e in eps if e["sim_date"] == y]
            if not pick:
                last_conv = eps[-1]["conv_id"]
                pick = [e for e in eps if e["conv_id"] == last_conv]
                note = f"(No conversation dated {y}; using the most recent earlier conversation, {pick[0]['sim_date']}.) "
        elif w == "last":
            last_conv = eps[-1]["conv_id"]
            pick = [e for e in eps if e["conv_id"] == last_conv]
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", w):
            pick = [e for e in eps if e["sim_date"] == w]
        if about:
            kw = [k for k in re.findall(r"\w+", about.lower()) if len(k) > 3]
            pick = [e for e in pick if any(k in (e["question"] + e["summary"]).lower() for k in kw)] or pick
        rows = [{"date": e["sim_date"], "question": e["question"], "wells": ", ".join(e["entities"]),
                 "answer_summary": e["summary"][:400]} for e in pick[-8:]]
        summ = note + f"{user['name']}'s earlier conversations:\n" + "\n".join(
            f"- [{r['date']}] Q: {r['question']} | wells: {r['wells']} | A: {r['answer_summary']}" for r in rows)
        return {"summary": summ, "rows": rows, "sources": [{"kind": "conversation", "id": e["conv_id"],
                                                            "date": e["sim_date"]} for e in pick[-8:]]}

    # ------------------------------------------------------------------ tool dispatch
    def call_tool(self, name, args, user, conv):
        e = self.eng
        args = {k: v for k, v in (args or {}).items() if v not in (None, "", [])}
        if name == "recall_my_conversations":
            return self.recall(user, conv, args.get("when"), args.get("about"))
        if name == "save_my_preference":
            self.store.add_preference(user["user_id"], args["text"])
            return {"summary": f"Saved private preference for {user['name']}: {args['text']}", "rows": [], "sources": [],
                    "memory_write": {"id": "PREF", "kind": "private_preference", "status": "applied", "conflicts": []}}
        if name == "record_feedback":
            out = feedback.record(e, user, conv_id=conv["conv_id"], **args)
            summ = "Recorded " + json.dumps({"assertion": {k: out["assertion"].get(k) for k in (
                "id", "kind", "asset_id", "inspection_id", "field", "old_value", "new_value", "rule_key", "well_type",
                "equipment_kind", "status")}, "record": out.get("record"), "checks": out["checks"],
                "conflicts": out["conflicts"], "consequences": out["consequences"]}, default=str)
            a = out["assertion"]
            return {"summary": summ, "rows": [], "sources": [e.src_fb(a)] + out.get("sources", []),
                    "memory_write": {"id": a["id"], "kind": a["kind"], "status": a["status"], "asset_id": a.get("asset_id"),
                                     "conflicts": out["conflicts"]}}
        if name in PROCEDURES:
            return getattr(procedures, name)(e, **args)
        fn = getattr(e, name, None)
        if fn is None or name.startswith("_"):
            raise ValueError(f"unknown tool {name}")
        return fn(**args)

    # ------------------------------------------------------------------ main loop
    def run(self, user: dict, conv: dict, text: str) -> dict:
        e = self.eng
        e.refresh()
        if self.llm is None:
            self.llm = LLM()
        history = self.store.messages(user["user_id"], conv["conv_id"])[-12:]
        sysmsg = SYSTEM.format(today=fmt_date(e.as_of), user_name=user["name"],
                               user_role=(user.get("role") or "").replace("_", " "),
                               user_team=e.d.teams.get(user.get("team_id"), {}).get("name", user.get("team_id")),
                               docs=", ".join(sorted(e.d.docs)),
                               areas=", ".join(f"{v['name']} ({k})" for k, v in e.d.areas.items()),
                               teams=", ".join(f"{t['name']} (lead {e.name(t.get('lead_user_id'))})" for t in e.d.teams.values()),
                               prefs=("Private preferences of " + user["name"] + ": " + "; ".join(self.store.preferences(user["user_id"])))
                               if self.store.preferences(user["user_id"]) else "")
        msgs = [{"role": "system", "content": sysmsg}]
        for m in history:
            if m["role"] in ("user", "assistant") and m["content"]:
                msgs.append({"role": m["role"], "content": m["content"][:3000]})
        msgs.append({"role": "user", "content": text})

        results, trace, sources, writes, chosen = {}, [], [], [], None
        final = ""
        for step in range(config.MAX_AGENT_STEPS):
            resp = self.llm.chat(msgs, TOOLS)
            if not resp["tool_calls"]:
                final = resp["content"].strip()
                break
            msgs.append({"role": "assistant", "content": resp["content"] or None, "tool_calls": [
                {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": json.dumps(c["arguments"])}}
                for c in resp["tool_calls"]]})
            for c in resp["tool_calls"]:
                name, args = c["name"], c["arguments"]
                if name == "show_visual":
                    chosen = {"result_id": args.get("result_id"), "component": args.get("component"),
                              "title": args.get("title")}
                    content = f"Visual set: {args.get('component')} for {args.get('result_id')}"
                else:
                    try:
                        r = self.call_tool(name, args, user, conv)
                        rid = f"r{len(results) + 1}"
                        r["result_id"] = rid
                        results[rid] = {"tool": name, "args": args, **r}
                        sources += r.get("sources", [])
                        if r.get("memory_write"):
                            writes.append(r["memory_write"])
                        content = json.dumps({"result_id": rid, "summary": r["summary"][:7000],
                                              "row_count": len(r.get("rows", [])),
                                              "suggested_visual": r.get("suggested_visual")}, default=str)
                    except Exception as ex:
                        content = json.dumps({"error": str(ex)})
                        trace.append({"tool": name, "args": args, "error": str(ex)})
                trace.append({"tool": name, "args": args})
                msgs.append({"role": "tool", "tool_call_id": c["id"], "content": content})
        else:
            resp = self.llm.chat(msgs + [{"role": "user", "content": "Write the final answer now from the tool results."}])
            final = resp["content"].strip()

        visual = self.pick_visual(text, results, chosen)
        tool_text = " ".join(json.dumps(r["summary"], default=str) + json.dumps(r.get("rows", [])[:200], default=str)
                             for r in results.values())
        unverified = sorted({i for i in re.findall(r"\b(?:WELL|INS|MNT|REG|CTX|FB)-\d{4}(?:-\d{3,5})?\b", final)
                             if i not in tool_text and i not in text})
        conflicts = []
        for w in writes:
            conflicts += w.get("conflicts", [])
        for r in results.values():
            for row in r.get("rows", [])[:5]:
                conflicts += row.get("conflicts", []) if isinstance(row.get("conflicts"), list) else []
        payload = {"visual": visual, "sources": _dedupe(sources)[:80], "memory_writes": writes,
                   "conflicts": list(dict.fromkeys(conflicts)), "trace": trace, "model": self.llm.last_model,
                   "unverified_ids": unverified}
        self.store.add_message(user["user_id"], conv["conv_id"], "user", text)
        self.store.add_message(user["user_id"], conv["conv_id"], "assistant", final, payload)
        wells = list(dict.fromkeys(re.findall(r"WELL-\d{4}", final)))
        if visual and len(visual["rows"]) <= 15:
            wells += [r.get("asset_id") for r in visual["rows"] if r.get("asset_id") and r.get("asset_id") not in wells]
        self.store.add_episode(user["user_id"], conv["conv_id"], conv.get("sim_date"), text, final[:800], wells[:20])
        fresh = self.store.conversation(user["user_id"], conv["conv_id"]) or {}
        if fresh.get("title") in (None, "", "New chat"):
            self.store.rename_conversation(user["user_id"], conv["conv_id"], text[:60])
            conv["title"] = text[:60]
        return clean_json({"content": final, **payload})

    def pick_visual(self, text, results, chosen):
        data_results = {k: v for k, v in results.items() if v.get("rows") and v["tool"] not in (
            "search_docs", "get_rules", "recall_my_conversations", "record_feedback", "list_documents", "read_document", "save_my_preference")}
        if not data_results:
            return None
        want = requested_visual(text)
        rid, comp, title = None, None, None
        if chosen and chosen.get("result_id") in data_results:
            rid, comp, title = chosen["result_id"], chosen.get("component"), chosen.get("title")
        if want:
            comp = want
            if rid is None:
                match = [k for k, v in data_results.items() if v.get("suggested_visual") == want]
                rid = match[-1] if match else list(data_results)[-1]
        if rid is None:
            rid = list(data_results)[-1]
            comp = data_results[rid].get("suggested_visual")
        if not comp:
            return None
        r = data_results[rid]
        rows = r["rows"]
        if comp == "map" and not any(k in (rows[0] if rows else {}) for k in ("lat",)):
            ids = {x.get("asset_id") for x in rows}
            W = self.eng.d.wells.set_index("asset_id")
            rows = [{**x, "lat": W.loc[x["asset_id"]].lat, "lon": W.loc[x["asset_id"]].lon} for x in rows
                    if x.get("asset_id") in W.index] if ids else rows
        return {"component": comp, "title": title or _title(r), "rows": rows[:500], "columns": r.get("columns"),
                "hints": r.get("hints", {}), "result_id": rid, "tool": r["tool"]}


def _title(r):
    a = r.get("args", {})
    bits = [a.get("area") or ", ".join(a.get("asset_ids", []) or []) or a.get("asset_id") or "",
            str(a.get("period") or "")]
    return f"{r['tool'].replace('_', ' ').title()} {' · '.join(b for b in bits if b)}".strip()


def _dedupe(src):
    seen, out = set(), []
    for s in src:
        if not s:
            continue
        k = (s.get("kind"), s.get("id") or s.get("doc"), s.get("section"))
        if k not in seen:
            seen.add(k)
            out.append(s)
    return out
