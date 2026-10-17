"""Procedure audits: deterministic checks of the Operations SOP (OPS-1..OPS-6), management-of-change
memos, supplier recall notices and regulator letters. Parameters (MOC well lists and expiries,
recalled lots, deadlines) are read from the documents in fleet/sops, not hard-coded per question.
"""
from __future__ import annotations

import re
from datetime import timedelta

import pandas as pd

from .engine import Engine, fmt_date, result, _ts

GAS = re.compile(r"gas odou?r|smell(?:ed)? (?:of )?gas|gas smell|rotten[- ]egg|h2s monitor alarm|h2s alarm", re.I)
BYPASS_IN = re.compile(r"bypass (?:in place|installed)|put the bypass in|had the bypass installed|bypass in\b", re.I)
BYPASS_OUT = re.compile(r"bypass (?:removed|pulled|out)|took the bypass out|bypass removed", re.I)
SHUT = re.compile(r"\bshut(?:-| )in\b|shut the well in", re.I)
RESTART = re.compile(r"^restarted\b|put back on production|back online|restarted .*unit running|restarted .*after", re.I)
WELL_ID = re.compile(r"WELL-\d{4}")
OPS4 = [("Installation error", ["installation", "installed incorrectly", "misaligned", "re-terminated", "not torqued", "cross-threaded"]),
        ("Sand", ["sand"]), ("Scale", ["scale", "paraffin"]), ("Gas interference", ["gas lock", "gas interference", "free gas"]),
        ("Corrosion", ["corrosion", "corroded"]), ("Electrical", ["winding", "insulation", "switch", "terminal box"]),
        ("Fatigue/wear", ["fatigue", "wear", "worn", "years of service", "buckling", "ageing", "vibration"])]


def _note_well(n) -> str:
    """OPS SOP: a round note names its well by ID in the text; prefer that over the filing well."""
    m = WELL_ID.search(n["text"] or "")
    return m.group(0) if m else n["asset_id"]


def _ops_notes(eng: Engine):
    N = eng.d.notes
    N = N[N.note_type == "operator_note"].copy()
    N["t"] = pd.to_datetime(N.created_at, utc=True)
    N["well"] = [_note_well(n) for n in N.to_dict("records")]
    return N.sort_values("t")


def _doc(eng: Engine, pattern: str) -> list[tuple[str, str]]:
    return [(k, v) for k, v in sorted(eng.d.docs.items()) if re.search(pattern, k, re.I)]


def _ops_rule(eng: Engine, pattern: str, default):
    for k, v in _doc(eng, r"operations-sop"):
        if m := re.search(pattern, v, re.S):
            return m, k
    return default, None


# ---------------------------------------------------------------------------------- OPS-1
def gas_odor_audit(eng: Engine, since: str | None = None, until: str | None = None):
    N = _ops_notes(eng)
    s = _ts(since) or N.t.min()
    e = (_ts(until) + timedelta(days=1)) if until else eng.as_of + timedelta(days=1)
    G = N[(N.t >= s) & (N.t < e) & N.text.str.contains(GAS)]
    # deadlines from the SOP: 24 h before the cut-over date, 12 h from it
    m, doc = _ops_rule(eng, r"\*\*(\d+) hours\*\* for reports noted before (\d{1,2} \w{3} \d{4});\s*-\s*\*\*(\d+) hours\*\* for reports noted from", None)
    old_h, cut, new_h = (float(m.group(1)), pd.Timestamp(m.group(2), tz="UTC"), float(m.group(3))) if m else (24.0, pd.Timestamp("2027-01-01", tz="UTC"), 12.0)
    M, I = eng.d.mnt, eng.d.ins
    rows, src = [], []
    for n in G.to_dict("records"):
        w, t = n["well"], n["t"]
        limit = old_h if t < cut else new_h
        jobs = M[(M.asset_id == w) & (M.start > t)].sort_values("start")
        insp = I[(I.asset_id == w) & (I.t > t) & (I.method == "manual")].sort_values("t")
        cands = []
        if len(jobs):
            j = jobs.iloc[0]
            cands.append((j.start, j.maintenance_id, "repair job"))
        if len(insp):
            i = insp.iloc[0]
            cands.append((i.t, i.inspection_id, "manual inspection"))
        resp = min(cands) if cands else None
        hrs = round((resp[0] - t).total_seconds() / 3600, 1) if resp else None
        met = resp is not None and hrs <= limit
        area = eng.wells.loc[w].area_id if w in eng.wells.index else None
        rows.append({"asset_id": w, "area": eng.d.area_name(area), "reported_at": t.strftime("%-d %b %Y %H:%M UTC"),
                     "note_id": n["note_id"], "note": n["text"], "operator": eng.name(n["author_user_id"]),
                     "response": f"{resp[1]} ({resp[2]}) {resp[0].strftime('%-d %b %Y %H:%M')}" if resp else "none",
                     "hours_to_response": hrs, "deadline_h": limit, "status": "Met" if met else "Missed"})
        src.append(eng.src_note({**n, "asset_id": n["asset_id"]}))
    src.append({"kind": "doc", "doc": doc or "sops/operations-sop-rev2.md", "section": "OPS-1 Gas odor response",
                "quote": f"Response (repair job start or manual inspection) within {old_h:g} h before {fmt_date(cut)}, {new_h:g} h from it; drone inspections do not count."})
    missed = [r for r in rows if r["status"] == "Missed"]
    summ = (f"OPS-1 gas odor reports in operator notes {fmt_date(s)} – {fmt_date(e - timedelta(days=1))}: {len(rows)}; "
            f"met {len(rows) - len(missed)}, missed {len(missed)}. Deadline {old_h:g} h for notes before {fmt_date(cut)}, {new_h:g} h from then. "
            "Response = first repair job started or first MANUAL inspection after the note (drone inspections don't count).")
    for r in rows:
        summ += f"\n- {r['asset_id']} ({r['area']}) {r['reported_at']} [{r['note_id']} by {r['operator']}: \"{r['note']}\"] → {r['response']}, {r['hours_to_response']} h vs {r['deadline_h']:g} h: {r['status']}"
    return result("gas_odor_audit", summ, rows, src, "table",
                  columns=["asset_id", "area", "reported_at", "response", "hours_to_response", "deadline_h", "status", "note_id"])


# ---------------------------------------------------------------------------------- OPS-2 + MOC
def moc_memos(eng: Engine) -> list[dict]:
    memos = []
    for k, v in _doc(eng, r"moc-"):
        mid = re.search(r"(MOC-\d{4}-\d+)", v)
        exp = re.search(r"expires on (\d{1,2} \w{3} \d{4})", v)
        eff = re.search(r"Effective from (\d{1,2} \w{3} \d{4})", v)
        ext = re.search(r"extends (MOC-\d{4}-\d+)", v)
        memos.append({"id": mid.group(1) if mid else k, "doc": k, "wells": sorted(set(WELL_ID.findall(v))),
                      "effective": _ts(eff.group(1)) if eff else None, "expires": _ts(exp.group(1)) if exp else None,
                      "extends": ext.group(1) if ext else None})
    for m in memos:  # an extension replaces the expiry of the memo it extends
        if m["extends"]:
            for base in memos:
                if base["id"] == m["extends"]:
                    base["expires"] = max(base["expires"], m["expires"]) if base["expires"] else m["expires"]
                    base["extended_by"] = m["id"]
                    if not m["effective"]:
                        m["effective"] = base["effective"]
    return memos


def bypass_audit(eng: Engine):
    memos = moc_memos(eng)
    N = _ops_notes(eng)
    B = N[N.text.str.contains(BYPASS_IN) | N.text.str.contains(BYPASS_OUT)]
    rows, src = [], []
    now_end = eng.as_of + timedelta(days=1)
    for w, g in B.groupby("well"):
        open_in = None
        spans = []
        for n in g.to_dict("records"):
            if BYPASS_OUT.search(n["text"]):
                if open_in is not None:
                    spans.append((open_in, n))
                    open_in = None
            elif BYPASS_IN.search(n["text"]) and open_in is None:
                open_in = n
        if open_in is not None:
            spans.append((open_in, None))
        for n_in, n_out in spans:
            cover = [m for m in memos if w in m["wells"]]
            memo = max(cover, key=lambda m: m["expires"] or pd.Timestamp.max.tz_localize("UTC")) if cover else None
            expiry_end = (memo["expires"] + timedelta(days=1)) if memo and memo["expires"] else None
            end = n_out["t"] if n_out is not None else now_end
            if memo is None:
                status = "Not approved"
            elif expiry_end is not None and end > expiry_end:
                status = "Expired"
            else:
                status = "Allowed"
            area = eng.wells.loc[w].area_id if w in eng.wells.index else None
            rows.append({"asset_id": w, "area": eng.d.area_name(area), "bypass_in": fmt_date(n_in["t"]),
                         "bypass_out": fmt_date(n_out["t"]) if n_out is not None else "still in",
                         "approval": (memo["id"] + (f" (extended by {memo['extended_by']})" if memo.get("extended_by") else "")) if memo else "none",
                         "approval_valid_until": fmt_date(memo["expires"]) if memo else "—", "status": status,
                         "in_place_now": n_out is None, "evidence": n_in["note_id"] + (f", {n_out['note_id']}" if n_out is not None else "")})
            src.append(eng.src_note(n_in))
            if n_out is not None:
                src.append(eng.src_note(n_out))
    for m in memos:
        src.append({"kind": "doc", "doc": m["doc"], "section": m["id"],
                    "quote": f"Wells {', '.join(m['wells'])}; effective {fmt_date(m['effective'])}; expires {fmt_date(m['expires'])}" + (f"; extends {m['extends']}" if m["extends"] else "")})
    rows.sort(key=lambda r: (not r["in_place_now"], r["area"] or "", r["asset_id"]))
    summ = ("OPS-2: a bypass is allowed only on a well named in an unexpired MOC (an extension replaces the expiry); it is a "
            "violation if the well is in no MOC or the bypass is still in after the expiry day. MOCs: " +
            "; ".join(f"{m['id']} wells {', '.join(m['wells'])} expires {fmt_date(m['expires'])}" + (f" (extends {m['extends']})" if m['extends'] else "")
                      + (f" (extended by {m.get('extended_by')})" if m.get("extended_by") else "") for m in memos))
    for r in rows:
        summ += f"\n- {r['asset_id']} ({r['area']}): in {r['bypass_in']}, out {r['bypass_out']}, approval {r['approval']} valid to {r['approval_valid_until']} → {r['status']} [{r['evidence']}]"
    return result("bypass_audit", summ, rows, src, "table",
                  columns=["asset_id", "area", "bypass_in", "bypass_out", "approval", "approval_valid_until", "status", "evidence"])


# ---------------------------------------------------------------------------------- OPS-3
def status_disagreements(eng: Engine, area: str | None = None):
    N = _ops_notes(eng)
    # OPS-3 status evidence = round notes, which name the well by ID in their text
    S = N[(N.text.str.contains(SHUT) | N.text.str.contains(RESTART)) & N.text.str.contains(WELL_ID)]
    ids = eng.scope_wells(area)
    rows, src = [], []
    for w in ids:
        if w not in eng.latest.index or eng.latest.loc[w].plugged:
            continue
        li = eng.latest.loc[w]
        sn = S[S.well == w]
        if sn.empty:
            continue
        n = sn.iloc[-1]
        note_says = "shut in" if SHUT.search(n.text) and not RESTART.search(n.text) else "restarted"
        note_prod = note_says == "restarted"
        if note_prod == bool(li.producing):
            continue
        if n.t > li.t:
            now = "Producing oil (unconfirmed)" if note_prod else "Not producing oil (shut in)"
            why = f"The operator note ({fmt_date(n.t)} {n.t.strftime('%H:%M')}) is more recent than the inspection ({fmt_date(li.t)}); OPS-3."
        else:
            now = "Producing oil" if li.producing else "Not producing oil"
            why = f"The inspection ({fmt_date(li.t)}) is more recent than the note; OPS-3."
        rows.append({"asset_id": w, "area": eng.d.area_name(li.area_id),
                     "latest_inspection": f"{li.inspection_id}, {fmt_date(li.t)} {li.t.strftime('%H:%M')}: {li.delta_c} °C above air vs {li.threshold_c:g} → {'producing' if li.producing else 'not producing'}"
                                          + (f" (corrected {li.corrected_by})" if li.corrected_by else ""),
                     "latest_operator_note": f"{n.note_id}, {fmt_date(n.t)} {n.t.strftime('%H:%M')}: \"{n.text}\"",
                     "status_now": now, "why": why})
        src += [eng.src_ins(li), eng.src_note(n.to_dict())]
    src.append({"kind": "doc", "doc": "sops/operations-sop-rev2.md", "section": "OPS-3 Status evidence precedence",
                "quote": "Status comes from the most recent of the latest inspection reading and the latest shut-in/restart operator note; a restart note is unconfirmed until an inspection confirms it."})
    summ = f"OPS-3 wells where the latest inspection and the latest shut-in/restart operator note disagree: {len(rows)}."
    for r in rows:
        summ += f"\n- {r['asset_id']} ({r['area']}): inspection {r['latest_inspection']} | note {r['latest_operator_note']} → {r['status_now']}. {r['why']}"
    return result("status_disagreements", summ, rows, src, "table",
                  columns=["asset_id", "area", "latest_inspection", "latest_operator_note", "status_now"])


# ---------------------------------------------------------------------------------- recall
def recall_info(eng: Engine) -> dict:
    for k, v in _doc(eng, r"recall"):
        lots = re.findall(r"^- (LOT-[\w-]+)\s*$", v, re.M)
        model = re.search(r"(Highline [\w-]+|[A-Z][\w]+ RP-\d+)", v)
        due = re.search(r"by (\d{1,2} \w{3} \d{4})", v)
        return {"doc": k, "lots": lots, "model": model.group(1) if model else None, "due": _ts(due.group(1)) if due else None}
    return {"doc": None, "lots": [], "model": None, "due": None}


def recalled_pumps(eng: Engine, area: str | None = None, team: str | None = None):
    info = recall_info(eng)
    REP = eng.d.reports
    M = eng.d.mnt.set_index("maintenance_id", drop=False)
    P = REP[REP.part_lot.notna()].copy()
    P["start"] = P.maintenance_id.map(lambda i: M.loc[i].start if i in M.index else pd.NaT)
    P = P.sort_values("start")
    ids = set(eng.scope_wells(area))
    rows, src = [], []
    for w, g in P.groupby("asset_id"):
        if w not in ids:
            continue
        wr = eng.wells.loc[w]
        if wr.status == "plugged_and_abandoned":
            continue
        if team:
            tname = eng.d.teams.get(wr.team_id, {}).get("name", wr.team_id)
            if team.lower() not in (str(wr.team_id).lower(), str(tname).lower()):
                continue
        cur = g.iloc[-1]  # the pump in the well today = the last one installed
        if cur.part_lot not in info["lots"]:
            continue
        job = M.loc[cur.maintenance_id]
        claims = [a for a in eng.feedback if a.get("asset_id") == w and a["kind"] in ("well_fact", "status_claim")
                  and re.search(r"pump|swap|replac", a["text"] or "", re.I)]
        claim_txt = "; ".join(f"{eng.name(a['author_user_id'])} said \"{a['text']}\" ({a['id']}, {a['status']}, {a['created_at'][:10]})" for a in claims)
        rows.append({"asset_id": w, "area": eng.d.area_name(wr.area_id),
                     "team": eng.d.teams.get(wr.team_id, {}).get("name", wr.team_id),
                     "pump": cur.parts_installed, "lot": cur.part_lot, "serial": cur.part_serial,
                     "installed_by_job": cur.maintenance_id, "installed_on": fmt_date(job.start),
                     "install_cost_usd": int(job.cost_total), "install_cost_kusd": round(job.cost_total / 1000, 1),
                     "producing_now": bool(eng.latest.loc[w].producing) if w in eng.latest.index else None,
                     "reported_by_people": claim_txt or None,
                     "status": "reported replaced (no work order yet)" if claims else "still in the ground"})
        src += [eng.src_report(cur.maintenance_id), eng.src_mnt(job.to_dict())]
        src += [eng.src_fb(a) for a in claims]
    src.append({"kind": "doc", "doc": info["doc"], "section": "What is recalled",
                "quote": f"{info['model']} lots {', '.join(info['lots'])}; replace by {fmt_date(info['due'])}; only the pump in the well today matters."})
    rows.sort(key=lambda r: (r["area"], r["asset_id"]))
    in_ground = [r for r in rows if r["status"] == "still in the ground"]
    by_area = {}
    for r in in_ground:
        by_area[r["area"]] = by_area.get(r["area"], 0) + 1
    summ = (f"Recall {info['doc']}: lots {', '.join(info['lots'])} must be replaced by {fmt_date(info['due'])}. The pump in a well today is the one "
            f"from its latest repair report with a 'Parts installed' line. Recalled pumps still in the ground per the records: {len(in_ground)} "
            f"({', '.join(f'{k}: {v}' for k, v in sorted(by_area.items()))}).")
    for r in rows:
        summ += (f"\n- {r['asset_id']} ({r['area']}, {r['team']}): {r['pump']} installed {r['installed_on']} by {r['installed_by_job']} "
                 f"(cost USD {r['install_cost_usd']:,}); producing now: {r['producing_now']}; {r['status']}"
                 + (f"; people said: {r['reported_by_people']}" if r['reported_by_people'] else ""))
    return result("recalled_pumps", summ, rows, src, "table",
                  columns=["asset_id", "area", "lot", "installed_by_job", "installed_on", "install_cost_usd", "producing_now", "status", "reported_by_people"])


# ---------------------------------------------------------------------------------- regulator letter
def spill_followup_audit(eng: Engine, areas: list[str] | str, since: str, required_phrase: str,
                         min_volume: float | None = None):
    """Reportable spills in some areas since a date whose clean-up report must contain a phrase
    (e.g. a regulator letter asking for lab soil samples)."""
    if isinstance(areas, str):
        areas = [a for a in re.split(r",|;| and ", areas) if a.strip()]
    ids = set()
    for a in areas:
        ids |= set(eng.scope_wells(a.strip()))
    rep_min = float(min_volume) if min_volume is not None else eng.rule("spill_reportable_bbl")[0]
    s = _ts(since)
    I = eng.I
    S = I[I.asset_id.isin(ids) & I.spill_detected.fillna(False) & (I.t >= s) & (I.t < eng.as_of + timedelta(days=1))]
    rows, src = [], []
    for r in S.sort_values("t").to_dict("records"):
        if not r["real_spill"]:
            continue
        if (r["spill_est_volume_bbl"] or 0) < rep_min:
            continue
        jobs = eng.d.mnt[eng.d.mnt.triggered_by_inspection_id == r["inspection_id"]]
        rep = eng.d.reports[eng.d.reports.maintenance_id.isin(jobs.maintenance_id)]
        has = bool(len(rep)) and rep.text.str.contains(re.escape(required_phrase), case=False).any()
        reason = ("report contains \"" + required_phrase + "\"") if has else (
            "no clean-up report on record" if rep.empty else f"clean-up report {', '.join(rep.maintenance_id)} lacks \"{required_phrase}\"")
        rows.append({"asset_id": r["asset_id"], "area": eng.d.area_name(r["area_id"]),
                     "inspection": f"{r['inspection_id']} ({fmt_date(r['t'])})", "volume_bbl": r["spill_est_volume_bbl"],
                     "ai_estimate_bbl": r["orig_spill_est_volume_bbl"] if r["corrected_by"] else None,
                     "cleanup_job": ", ".join(jobs.maintenance_id) or "none",
                     "compliant": "Yes" if has else "No", "reason": reason})
        src.append(eng.src_ins(r))
        src += [eng.src_report(m) for m in rep.maintenance_id]
    excluded = S[~S.real_spill & (S.spill_est_volume_bbl >= rep_min)]
    summ = (f"Reportable spills (≥ {rep_min:g} bbl, effective volume after corrections) in {', '.join(areas)} since {fmt_date(s)}: {len(rows)}; "
            f"non-compliant {sum(r['compliant'] == 'No' for r in rows)}. Compliant only if the clean-up report contains \"{required_phrase}\".")
    if len(excluded):
        summ += " Excluded as confirmed not crude: " + ", ".join(f"{x.inspection_id} ({x.corrected_not_spill})" for x in excluded.itertuples()) + "."
    for r in rows:
        summ += f"\n- {r['asset_id']} ({r['area']}) {r['inspection']} {r['volume_bbl']} bbl, job {r['cleanup_job']}: compliant {r['compliant']} — {r['reason']}"
    return result("spill_followup_audit", summ, rows, src, "table",
                  columns=["asset_id", "area", "inspection", "volume_bbl", "cleanup_job", "compliant", "reason"])


# ---------------------------------------------------------------------------------- OPS-5
def freeze_protection_audit(eng: Engine, start: str | None = None, end: str | None = None, threshold_c: float = -5.0,
                            within_days: int = 7):
    s = _ts(start) or pd.Timestamp(f"{eng.as_of.year - (1 if eng.as_of.month < 12 else 0)}-12-01", tz="UTC")
    e = (_ts(end) + timedelta(days=1)) if end else eng.as_of + timedelta(days=1)
    I = eng.I
    X = I[(I.t >= s) & (I.t < e) & (I.ambient_temp_c <= threshold_c) & I.producing & I.t.dt.month.isin([12, 1, 2])]
    M = eng.d.mnt
    H = M[M.issue.str.contains("heat trace check", case=False, na=False)]
    rows, src = [], []
    for r in X.sort_values("t").to_dict("records"):
        h = H[(H.asset_id == r["asset_id"]) & (H.start >= r["t"]) & (H.start <= r["t"] + timedelta(days=within_days))]
        due = r["t"] + timedelta(days=within_days)
        st = "Met" if len(h) else ("Missed" if due < eng.as_of + timedelta(days=1) else "Pending")
        rows.append({"asset_id": r["asset_id"], "area": eng.d.area_name(r["area_id"]), "inspection": r["inspection_id"],
                     "date": fmt_date(r["t"]), "ambient_temp_c": r["ambient_temp_c"], "delta_c": r["delta_c"],
                     "heat_trace_check": f"{h.iloc[0].maintenance_id} {fmt_date(h.iloc[0].start)}" if len(h) else "none",
                     "due_by": fmt_date(due), "status": st})
        src.append(eng.src_ins(r))
    src.append({"kind": "doc", "doc": "sops/operations-sop-rev2.md", "section": "OPS-5 Freeze protection",
                "quote": "1 Dec–28 Feb: a producing well read at ambient ≤ −5 °C needs a 'Heat trace check' job starting within 7 days."})
    missed = [r for r in rows if r["status"] == "Missed"]
    summ = f"OPS-5 cold readings ({fmt_date(s)} – {fmt_date(e - timedelta(days=1))}, ambient ≤ {threshold_c:g} °C on producing wells): {len(rows)}; missed checks {len(missed)}."
    for r in rows[:80]:
        summ += f"\n- {r['asset_id']} ({r['area']}) {r['inspection']} {r['date']} air {r['ambient_temp_c']} °C → check {r['heat_trace_check']} (due {r['due_by']}): {r['status']}"
    return result("freeze_protection_audit", summ, rows, src, "table")


# ---------------------------------------------------------------------------------- OPS-4 / OPS-6
def classify_root_cause(text: str | None) -> str:
    t = (text or "").lower()
    for cat, kws in OPS4:
        if any(k in t for k in kws):
            return cat
    return "Other"


def failure_analysis(eng: Engine, period: str = "this_year", area: str | None = None, equipment_kind: str | None = None):
    s, e, label = eng.period(period)
    ids = set(eng.scope_wells(area))
    M = eng.d.mnt
    C = M[(M.maintenance_type == "corrective") & M.asset_id.isin(ids)].sort_values("start")
    if equipment_kind:
        C = C[C.equipment_kind == equipment_kind]
    REP = eng.d.reports.set_index("maintenance_id")
    rows = []
    prev = {}
    for j in C.to_dict("records"):
        key = (j["asset_id"], j["equipment_kind"])
        rc = REP.loc[j["maintenance_id"]].root_cause if j["maintenance_id"] in REP.index else None
        cat = classify_root_cause(rc)
        p = prev.get(key)
        repeat = p is not None and j["start"] <= p["end"] + timedelta(days=30)
        if s <= j["start"] < e:
            rows.append({"asset_id": j["asset_id"], "area": eng.d.area_name(eng.wells.loc[j["asset_id"]].area_id),
                         "maintenance_id": j["maintenance_id"], "started": fmt_date(j["start"]), "equipment_kind": j["equipment_kind"],
                         "category": cat, "repeat_failure": repeat,
                         "previous_job": p["maintenance_id"] if repeat else None,
                         "charged_to": ((p.get("contractor") or "company crew") if repeat and cat == "Installation error" else None)})
        prev[key] = j
    df = pd.DataFrame(rows)
    summ = f"OPS-4/OPS-6 corrective jobs started {label}: {len(rows)}."
    if len(df):
        summ += "\nBy category: " + ", ".join(f"{k}: {v}" for k, v in df.category.value_counts().items())
        rep = df[df.repeat_failure]
        summ += f"\nRepeat failures (≤30 days after previous on same equipment): {len(rep)}."
        ch = rep[rep.charged_to.notna()]
        if len(ch):
            summ += " Counted against crews (installation error): " + ", ".join(f"{k}: {v}" for k, v in ch.charged_to.value_counts().items())
    src = [{"kind": "doc", "doc": "sops/operations-sop-rev2.md", "section": "OPS-4 / OPS-6", "quote": "First matching keyword row in order gives the category; repeat = same well+equipment within 30 days after previous completed."}]
    return result("failure_analysis", summ, rows, src, "table")


# ---------------------------------------------------------------------------------- shut-in delays
RE_PARTS_DELAY = re.compile(r"(?:stayed|stay) shut in for about ([\d.]+) days? longer than the repair itself because the replacement part (?:was|is) back-ordered", re.I)
RE_RIG_DELAY = re.compile(r"([^.]*?)workover rig was busy on other wells, so the well waited about ([\d.]+) days?", re.I)
RE_WEATHER = re.compile(r"weather[^.]*?(?:about ([\d.]+) days?|about a week)?", re.I)


def shut_in_delays(eng: Engine, period: str = "this_year", area: str | None = None):
    """Why wells stay shut in longer than the repair: parsed from the repair reports (parts back-ordered,
    company rig busy = crews, contractor rig busy = contractors, weather if a report says so)."""
    s, e, label = eng.period(period)
    ids = set(eng.scope_wells(area))
    M = eng.d.mnt.set_index("maintenance_id", drop=False)
    REP = eng.d.reports
    jobs = []
    for r in REP.itertuples():
        if r.asset_id not in ids or r.maintenance_id not in M.index:
            continue
        j = M.loc[r.maintenance_id]
        if not (s <= j.start < e):
            continue
        reason, days = None, None
        if m := RE_PARTS_DELAY.search(r.text):
            reason, days = "Parts", float(m.group(1))
        elif m := RE_RIG_DELAY.search(r.text):
            who = m.group(1).strip()
            reason, days = ("Crews" if re.search(r"\bcompany\b", who, re.I) else "Contractors"), float(m.group(2))
        elif m := re.search(r"weather[^.]*?([\d.]+) days?", r.text, re.I):
            reason, days = "Weather", float(m.group(1))
        if reason:
            jobs.append({"asset_id": r.asset_id, "area": eng.d.area_name(eng.wells.loc[r.asset_id].area_id),
                         "maintenance_id": r.maintenance_id, "started": fmt_date(j.start), "reason": reason, "extra_days": days,
                         "contractor": j.contractor})
    df = pd.DataFrame(jobs)
    rows = []
    if len(df):
        for (a, rsn), g in df.groupby(["area", "reason"]):
            rows.append({"area": a, "reason": rsn, "jobs": len(g), "share_pct": round(100 * len(g) / (df.area == a).sum(), 1),
                         "median_extra_days": float(g.extra_days.median()), "mean_extra_days": round(float(g.extra_days.mean()), 1)})
    rows.sort(key=lambda x: (x["area"], -x["jobs"]))
    N = eng.d.notes
    wn = N[N.text.str.contains("weather", case=False, na=False) & (pd.to_datetime(N.created_at, utc=True) >= s)
           & (pd.to_datetime(N.created_at, utc=True) < e) & N.asset_id.isin(ids)]
    summ = (f"Jobs started {label} where the well stayed shut in longer than the repair, with the reason stated in the repair report: "
            f"{len(df)}. Reasons: parts back-ordered (Parts), company workover rig busy (Crews), contractor's rig busy (Contractors), weather.")
    if len(df):
        summ += "\nOverall: " + ", ".join(f"{k}: {v} jobs, median {df[df.reason == k].extra_days.median():g} extra days" for k, v in df.reason.value_counts().items())
        for a, g in df.groupby("area"):
            summ += f"\n- {a} ({len(g)} jobs): " + ", ".join(
                f"{k} {100 * v / len(g):.0f}% (median {g[g.reason == k].extra_days.median():g} d)" for k, v in g.reason.value_counts().items())
    summ += (f"\nWeather: no repair report in the period gives weather as the reason; {len(wn)} operator/supervisor notes mention weather "
             f"delays ({', '.join(wn.note_id.head(8))}) without a day count tied to a job.") if "Weather" not in set(df.reason if len(df) else []) else ""
    src = [eng.src_report(j["maintenance_id"]) for j in jobs[:60]] + [eng.src_note(n) for n in wn.to_dict("records")[:10]]
    return result("shut_in_delays", summ, rows, [x for x in src if x], "bar_chart", x="area", y="share_pct", stacked=True,
                  detail=jobs[:300])
