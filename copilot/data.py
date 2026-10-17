"""Ingestion: loads one or more dataset folders (sample + test) into DataFrames,
parses the free-text repair reports, extracts rules from the manuals and SOPs,
and builds a BM25 index over the documents.

Nothing here is tuned to specific wells or questions: well types, areas, users and
thresholds are all discovered from the files.
"""
from __future__ import annotations

import glob
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from rank_bm25 import BM25Okapi

from . import config

WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}


def _jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# --------------------------------------------------------------------------- reports
RE_HDR = re.compile(r"#\s*Maintenance Report\s*[—-]\s*(MNT-[\w-]+)")
RE_CONTAIN = re.compile(r"[Cc]ontained\s+(?:about|roughly|approximately|around|after)?\s*([\d.]+)\s*(?:hours|h)\b")
RE_CLASS = re.compile(r"\((minor|moderate|reportable|major) class\)", re.I)
RE_WRITTEN = re.compile(r"\*\*Report written:\*\*\s*([0-9]{1,2} \w{3} \d{4})")
RE_HSE = re.compile(r"HSE notified\s+([\d.]+)\s*hours", re.I)
RE_ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*$")


def parse_report(text: str) -> dict:
    out = {"report_mnt_id": None, "containment_hours": None, "stated_class": None,
           "report_written": None, "hse_notice_hours": None, "in_progress": "Work done so far" in text,
           "compliance": [], "root_cause": None, "action_required": False}
    if m := RE_HDR.search(text):
        out["report_mnt_id"] = m.group(1)
    if m := RE_CONTAIN.search(text):
        out["containment_hours"] = float(m.group(1).rstrip("."))
    if m := RE_CLASS.search(text):
        out["stated_class"] = m.group(1).lower()
    if m := RE_WRITTEN.search(text):
        out["report_written"] = m.group(1)
    if m := RE_HSE.search(text):
        out["hse_notice_hours"] = float(m.group(1))
    sec = re.search(r"## Compliance check\s*(.*?)(?:\n## |\Z)", text, re.S)
    if sec:
        for line in sec.group(1).splitlines():
            m = RE_ROW.match(line.strip())
            if m and m.group(1) not in ("Protocol",) and not set(m.group(1)) <= set("-: "):
                result = m.group(2).replace("*", "").strip()
                out["compliance"].append({"protocol": m.group(1), "result": result, "detail": m.group(3)})
                if result.lower() == "action required":
                    out["action_required"] = True
    rc = re.search(r"## Root cause\s*(.*?)(?:\n## |\Z)", text, re.S)
    if rc:
        out["root_cause"] = " ".join(rc.group(1).split())[:400]
    return out


# --------------------------------------------------------------------------- rules
@dataclass
class Rule:
    key: str
    value: float
    scope: dict
    doc: str
    section: str
    quote: str
    source: str = "manual"   # manual | sop | user
    author: str | None = None
    assertion_id: str | None = None


def _section_of(text: str, pos: int) -> str:
    heads = [(m.start(), m.group(1).strip()) for m in re.finditer(r"^#{2,3}\s+(.+)$", text, re.M)]
    cur = ""
    for start, h in heads:
        if start <= pos:
            cur = h
    return cur


def _sentence(text: str, pos: int) -> str:
    s = max(text.rfind("\n\n", 0, pos), text.rfind(". ", 0, pos))
    e = text.find("\n\n", pos)
    return " ".join(text[s + 1: e if e > 0 else pos + 300].split()).strip(" .")


def extract_well_type_rules(name: str, text: str) -> tuple[list[Rule], str | None]:
    """Reads thresholds out of a well-type manual. Returns rules + parent type it inherits from."""
    doc = f"well-types/{name}.md"
    rules: list[Rule] = []
    parent = None
    if m := re.search(r"(?:follow|follows) the (T\w+) manual|Same as (T\w+)", text):
        parent = m.group(1) or m.group(2)
    patterns = {
        "producing_delta_c": r"(?:producing|active)\W[^.]*?at least \**(\d+(?:\.\d+)?)\s*°C above",
        "temp_alarm_c": r"at or below (\d+(?:\.\d+)?)\s*°C",
        "spill_shutin_area_pct": r"more than (\d+(?:\.\d+)?)\s*%\s*of the pad",
        "downtime_report_days": r"more than (\d+) consecutive days",
    }
    for key, pat in patterns.items():
        if m := re.search(pat, text, re.S | re.I):
            rules.append(Rule(key, float(m.group(1)), {"well_type": name}, doc,
                              _section_of(text, m.start()), _sentence(text, m.start(1))))
    if m := re.search(r"(\w+) or more \**corrective\**", text, re.I):
        n = WORDS.get(m.group(1).lower()) or (int(m.group(1)) if m.group(1).isdigit() else None)
        if n:
            rules.append(Rule("rca_corrective_count", float(n), {"well_type": name}, doc,
                              _section_of(text, m.start()), _sentence(text, m.start())))
    return rules, parent


SOP_DEFAULTS = {
    # key: (default, regex, doc)
    "spill_minor_below_bbl": (1, r"\| Minor \| below (\d+(?:\.\d+)?) bbl", "sops/spill-response-sop.md"),
    "spill_reportable_bbl": (5, r"\| Reportable \| (\d+(?:\.\d+)?) bbl", "sops/spill-response-sop.md"),
    "spill_major_bbl": (25, r"\| Major \| (\d+(?:\.\d+)?) bbl", "sops/spill-response-sop.md"),
    "sr01_report_hours": (24, r"\*\*SR-01\*\*.*?within \*\*(\d+) hours\*\*", "sops/spill-response-sop.md"),
    "sr01_major_report_hours": (2, r"\*\*SR-01\*\*.*?or within \*\*(\d+) hours\*\* for a major", "sops/spill-response-sop.md"),
    "sr02_containment_hours": (4, r"\*\*SR-02\*\*.*?within \*\*(\d+) hours\*\*", "sops/spill-response-sop.md"),
    "sr03_verification_days": (60, r"\*\*verified within (\d+) days\*\*", "sops/spill-response-sop.md"),
    "hse_notice_hours": (72, r"notify HSE within (\d+) ?h", "sops/spill-response-sop.md"),
    "rc01_inspection_gap_days": (14, r"\*\*RC-01\*\*.*?every \*\*(\d+) days\*\*", "sops/regulatory-compliance-sop.md"),
    "rc04_nov_response_days": (30, r"\*\*RC-04\*\*.*?within \*\*(\d+) days\*\*", "sops/regulatory-compliance-sop.md"),
}


def extract_sop_rules(docs: dict[str, str]) -> list[Rule]:
    rules = []
    for key, (default, pat, doc) in SOP_DEFAULTS.items():
        text = docs.get(doc, "")
        m = re.search(pat, text, re.S)
        if m:
            rules.append(Rule(key, float(m.group(1)), {}, doc, _section_of(text, m.start()),
                              " ".join(text[m.start(): m.end() + 120].split())[:300], "sop"))
        else:
            rules.append(Rule(key, float(default), {}, doc, "", "(default; not found in document)", "sop"))
    return rules


# --------------------------------------------------------------------------- dataset
@dataclass
class Data:
    wells: pd.DataFrame
    ins: pd.DataFrame
    mnt: pd.DataFrame
    reg: pd.DataFrame
    notes: pd.DataFrame
    reports: pd.DataFrame
    areas: dict          # area_id -> {name, team_id, center}
    users: dict          # user_id -> {name, role, team_id}
    teams: dict          # team_id -> {name, lead_user_id}
    docs: dict           # relative doc path -> text
    rules: list[Rule]
    type_parent: dict    # well_type -> parent well_type
    as_of: pd.Timestamp
    chunks: list[dict] = field(default_factory=list)
    bm25: BM25Okapi | None = None
    load_report: dict = field(default_factory=dict)

    def area_name(self, area_id):
        return self.areas.get(area_id, {}).get("name", area_id)

    def user_name(self, uid):
        if uid is None or (isinstance(uid, float) and pd.isna(uid)):
            return None
        return self.users.get(uid, {}).get("name", uid)

    def search(self, query: str, k: int = 6, asset_id: str | None = None) -> list[dict]:
        toks = _tok(query)
        if not toks or self.bm25 is None:
            return []
        scores = self.bm25.get_scores(toks)
        order = sorted(range(len(scores)), key=lambda i: -scores[i])
        out = []
        for i in order:
            c = self.chunks[i]
            if asset_id and c.get("asset_id") not in (None, asset_id):
                continue
            if scores[i] <= 0:
                break
            out.append({**c, "score": round(float(scores[i]), 2)})
            if len(out) >= k:
                break
        return out


def _tok(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", s.lower())


def _chunk_doc(path: str, text: str, asset_id=None, kind="manual") -> list[dict]:
    out = []
    parts = re.split(r"(?m)^(?=#{1,3} )", text)
    for p in parts:
        if not p.strip():
            continue
        head = p.strip().splitlines()[0].lstrip("# ").strip()
        out.append({"doc": path, "section": head, "text": p.strip()[:2500], "asset_id": asset_id, "kind": kind})
        # each protocol row of a table becomes its own chunk too (SR-01, RC-04 ...)
        for line in p.splitlines():
            m = re.match(r"^\|\s*\**([A-Z]{2}-\d{2})\**\s*\|(.*)$", line.strip())
            if m:
                out.append({"doc": path, "section": m.group(1), "text": line.strip(), "asset_id": asset_id,
                            "kind": kind})
    return out


def load(dirs: list[str] | None = None) -> Data:
    t0 = time.time()
    dirs = [config.resolve_dir(d) for d in (dirs or config.DATA_DIRS)]
    areas, users, teams, docs = {}, {}, {}, {}
    meta, ins, mnt, reg, notes, reps, chunks = [], [], [], [], [], [], []
    type_rules: dict[str, list[Rule]] = {}
    type_parent: dict[str, str] = {}
    for root in dirs:
        fleet = root / "fleet"
        if (fleet / "areas.json").exists():
            a = json.loads((fleet / "areas.json").read_text(encoding="utf-8"))
            for ar in a.get("areas", []):
                prev = areas.get(ar["area_id"], {"asset_ids": []})
                areas[ar["area_id"]] = {**ar, "asset_ids": sorted(set(prev["asset_ids"]) | set(ar.get("asset_ids", [])))}
            for t in a.get("teams", []):
                teams[t["team_id"]] = t
        if (fleet / "users.json").exists():
            for u in json.loads((fleet / "users.json").read_text(encoding="utf-8")).get("users", []):
                users[u["user_id"]] = u
        for md in sorted(glob.glob(str(fleet / "**" / "*.md"), recursive=True)):
            rel = os.path.relpath(md, fleet)
            docs[rel] = Path(md).read_text(encoding="utf-8")
        for wt_md in sorted(glob.glob(str(fleet / "well-types" / "*.md"))):
            name = Path(wt_md).stem
            rules, parent = extract_well_type_rules(name, Path(wt_md).read_text(encoding="utf-8"))
            type_rules[name] = rules
            if parent and parent != name:
                type_parent[name] = parent
        for wd in sorted(glob.glob(str(root / "assets" / "*"))):
            if not os.path.exists(f"{wd}/metadata.json"):
                continue
            m = json.load(open(f"{wd}/metadata.json", encoding="utf-8"))
            meta.append(m)
            ins += _jsonl(f"{wd}/inspections.jsonl")
            mrows = _jsonl(f"{wd}/maintenance.jsonl")
            mnt += mrows
            reg += _jsonl(f"{wd}/regulatory-events.jsonl")
            notes += _jsonl(f"{wd}/context.jsonl")
            for r in mrows:
                rf = r.get("report_file")
                if not rf:
                    continue
                p = Path(wd) / rf
                if not p.exists():
                    continue
                text = p.read_text(encoding="utf-8")
                parsed = parse_report(text)
                reps.append({"maintenance_id": r["maintenance_id"], "asset_id": r["asset_id"],
                             "report_file": f"assets/{m['asset_id']}/{rf}", "text": text, **parsed})
                chunks += _chunk_doc(f"assets/{m['asset_id']}/{rf}", text, m["asset_id"], "report")

    for path, text in docs.items():
        chunks += _chunk_doc(path, text, None, "manual" if path.startswith("well-types") else "sop")

    # rules: inherit missing keys from the parent type (T350 -> T200)
    rules: list[Rule] = []
    for wt, rs in type_rules.items():
        have = {r.key for r in rs}
        rules += rs
        parent, seen = type_parent.get(wt), set()
        while parent and parent in type_rules and parent not in seen:
            seen.add(parent)
            for r in type_rules[parent]:
                if r.key not in have:
                    rules.append(Rule(r.key, r.value, {"well_type": wt}, r.doc, r.section,
                                      r.quote + f" (inherited by {wt})", r.source))
                    have.add(r.key)
            parent = type_parent.get(parent)
    rules += extract_sop_rules(docs)

    wells = pd.DataFrame([{
        "asset_id": m["asset_id"], "name": m.get("name"), "well_type": m.get("well_type"),
        "area_id": m.get("area_id"), "team_id": m.get("team_id"), "in_charge_user_id": m.get("in_charge_user_id"),
        "lat": (m.get("location") or {}).get("lat"), "lon": (m.get("location") or {}).get("lon"),
        "installed_on": m.get("installed_on"), "recorded_status": m.get("recorded_status"),
        "equipment": m.get("equipment", []),
    } for m in meta]).drop_duplicates("asset_id", keep="last").reset_index(drop=True)
    # wells whose area isn't listed in areas.json still get an area entry
    for aid in wells.area_id.dropna().unique():
        areas.setdefault(aid, {"area_id": aid, "name": aid, "asset_ids": []})

    I = pd.DataFrame(ins).drop_duplicates("inspection_id", keep="last")
    I["t"] = pd.to_datetime(I.inspected_at, utc=True)
    M = pd.DataFrame(mnt).drop_duplicates("maintenance_id", keep="last")
    M["start"] = pd.to_datetime(M.started_at, utc=True)
    M["end"] = pd.to_datetime(M.completed_at, utc=True)
    M["cost_total"] = M.cost_usd.apply(lambda c: (c or {}).get("total", 0) if isinstance(c, dict) else 0)
    M["cost_labor"] = M.cost_usd.apply(lambda c: (c or {}).get("labor", 0) if isinstance(c, dict) else 0)
    M["cost_parts"] = M.cost_usd.apply(lambda c: (c or {}).get("parts", 0) if isinstance(c, dict) else 0)
    R = pd.DataFrame(reg) if reg else pd.DataFrame(columns=["event_id", "asset_id", "date", "event_type"])
    R = R.drop_duplicates("event_id", keep="last")
    R["d"] = pd.to_datetime(R.date, utc=True)
    N = pd.DataFrame(notes) if notes else pd.DataFrame(columns=["note_id", "asset_id", "note_type", "text"])
    N = N.drop_duplicates("note_id", keep="last")
    if "inspection_id" not in N:
        N["inspection_id"] = None
    # notes that name an inspection only in their text (e.g. "Inspection INS-0101-0197: ...")
    N["linked_inspection_id"] = [
        iid if isinstance(iid, str) else (re.search(r"INS-\d{4}-\d{3,5}", t or "") or [None])[0]
        for iid, t in zip(N.inspection_id, N.text)]
    REP = pd.DataFrame(reps)

    as_of = pd.Timestamp(config.AS_OF, tz="UTC") if config.AS_OF else \
        (I.t.max().normalize() + pd.Timedelta(days=1))

    bm25 = BM25Okapi([_tok(c["section"] + " " + c["text"]) for c in chunks]) if chunks else None
    parsed_contain = int(REP.containment_hours.notna().sum()) if len(REP) else 0
    spill_reports = int(REP.text.str.contains("Spill clean-up").sum()) if len(REP) else 0
    data = Data(wells, I, M, R, N, REP, areas, users, teams, docs, rules, type_parent, as_of, chunks, bm25)
    data.load_report = {
        "dirs": [str(d) for d in dirs], "wells": len(wells), "areas": {a: v["name"] for a, v in areas.items()},
        "well_types": sorted(wells.well_type.dropna().unique().tolist()),
        "inspections": len(I), "repairs": len(M), "reports": len(REP), "regulator_events": len(R),
        "notes": len(N), "users": len(users), "as_of": str(as_of.date()),
        "first_inspection": str(I.t.min().date()), "last_inspection": str(I.t.max().date()),
        "spill_reports_with_containment": f"{parsed_contain}/{spill_reports}",
        "rules": [(r.key, r.scope.get("well_type", "*"), r.value) for r in rules],
        "types_without_threshold": sorted(set(wells.well_type.dropna()) - {
            r.scope.get("well_type") for r in rules if r.key == "producing_delta_c"}),
        "seconds": round(time.time() - t0, 1),
    }
    return data
