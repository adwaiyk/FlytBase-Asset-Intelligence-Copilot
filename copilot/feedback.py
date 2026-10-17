"""Write path: turns what a user tells the copilot into an assertion, after
resolving the exact record in code and checking it against the data and
against what other people said (conflict engine).

Kinds:
  correct_reading      raw-data correction of an inspection field (wellhead/ambient temperature)
  correct_spill_volume correction of the AI's spill-volume estimate
  not_a_spill          a detection that was not crude (water, shadow, mud)
  scoped_rule          a rule for one well, an area or a whole well type
  well_fact            something about a well's state or plans, shared with everyone
"""
from __future__ import annotations

import json
import re
from datetime import timedelta

import pandas as pd

from .engine import Engine, NOT_RUNNING_WORDS, fmt_date, _ts

RULE_KEYS = {"rca_corrective_count", "producing_delta_c", "sr02_containment_hours", "sr01_report_hours",
             "spill_reportable_bbl", "temp_alarm_c"}


def _find_inspection(eng: Engine, asset_id: str, inspection_id=None, date=None, spill_only=False):
    I = eng.I
    if inspection_id:
        r = I[I.inspection_id == inspection_id]
        if r.empty:
            raise ValueError(f"No inspection {inspection_id}")
        return r.iloc[0]
    X = I[I.asset_id == asset_id]
    if spill_only:
        X = X[X.spill_detected.fillna(False)]
    if date:
        d = _ts(date)
        if d is not None and d.year < 2000:  # "15 Oct" parsed without a year
            d = d.replace(year=eng.as_of.year)
        X = X[(X.t >= d.normalize()) & (X.t < d.normalize() + timedelta(days=1))]
    if X.empty:
        raise ValueError(f"No {'spill ' if spill_only else ''}inspection found for {asset_id} on {date}")
    return X.sort_values("t").iloc[-1]


def record(eng: Engine, user: dict, kind: str, text: str, asset_id: str | None = None,
           inspection_id: str | None = None, date: str | None = None, field: str | None = None,
           new_value: float | None = None, rule_key: str | None = None, well_type: str | None = None,
           area: str | None = None, equipment_kind: str | None = None, claimed_state: str | None = None,
           valid_from: str | None = None, valid_to: str | None = None, rationale: str | None = None,
           conv_id: str | None = None, second_hand_from: str | None = None) -> dict:
    st = eng.store
    uid = user["user_id"]
    aid = eng.resolve_well(asset_id) if asset_id else None
    out = {"checks": [], "conflicts": [], "consequences": []}

    if kind in ("correct_reading", "correct_spill_volume", "not_a_spill"):
        if not aid:
            raise ValueError("asset_id is required")
        spill = kind != "correct_reading"
        r = _find_inspection(eng, aid, inspection_id, date, spill_only=spill)
        iid = r.inspection_id
        if kind == "correct_reading":
            field = field if field in ("wellhead_temp_c", "ambient_temp_c") else "wellhead_temp_c"
        elif kind == "correct_spill_volume":
            field = "spill_est_volume_bbl"
        old = r[f"orig_{field}"] if field and f"orig_{field}" in r else None
        before = {"producing": bool(r.producing), "delta_c": r.delta_c, "class": r.spill_class,
                  "volume": r.spill_est_volume_bbl}
        # conflicts with other people's corrections of the same value
        for a in eng.feedback:
            if a.get("inspection_id") == iid and a.get("field") == field and a["status"] == "applied" and \
                    new_value is not None and str(a["new_value"]) != str(new_value):
                out["conflicts"].append(f"{eng.name(a['author_user_id'])} earlier corrected this to {a['new_value']} ({a['id']}).")
        a = st.add_assertion(kind="not_a_spill" if kind == "not_a_spill" else
                             ("correction_raw" if kind == "correct_reading" else "correction_ai"),
                             asset_id=aid, inspection_id=iid, field=field,
                             old_value=None if old is None or pd.isna(old) else str(old),
                             new_value=None if new_value is None else str(float(new_value)), text=text,
                             rationale=rationale, author_user_id=uid, valid_from=str(r.t.date()),
                             status="applied", conflicts=out["conflicts"], conv_id=conv_id)
        eng.refresh(force=True)
        r2 = eng.I[eng.I.inspection_id == iid].iloc[0]
        out["assertion"] = a
        out["record"] = {"inspection_id": iid, "date": fmt_date(r.t), "field": field, "original_value": old,
                         "corrected_value": new_value, "corrected_by": user["name"], "reason": rationale or text}
        if kind == "correct_reading":
            out["consequences"].append(
                f"{iid} ({fmt_date(r.t)}): wellhead {r2.wellhead_temp_c} °C vs air {r2.ambient_temp_c} °C = "
                f"{r2.delta_c} °C above air vs limit {r2.threshold_c} → {'PRODUCING' if r2.producing else 'NOT producing'} "
                f"(before the correction: {before['delta_c']} °C, {'producing' if before['producing'] else 'not producing'}). "
                f"Original value {old} kept for reference.")
            if r.notes and NOT_RUNNING_WORDS.search(r.notes) and r2.producing:
                out["conflicts"].append(
                    f"The same inspection has the inspector's remark \"{r.notes}\" ({eng.name(r.inspector_user_id)}), "
                    f"which disagrees with the corrected reading. Ask {user['name']} to confirm.")
            t_s = f"{r.t.day} {r.t.strftime('%b %Y %H:%M')}"
            out["consequences"].append(
                f"{iid} ({t_s} UTC): volume {new_value} bbl (AI estimate {old} kept for reference) → "
                f"class '{r2.spill_class}' (was '{before['class']}').")
            audit = eng.compliance_audit(asset_id=aid, start=str(r.t.date()), end=str(r.t.date()))
            out["consequences"].append(audit["summary"])
            out["sources"] = audit["sources"]
        else:
            out["consequences"].append(f"{iid} no longer counts as a spill for reporting or statistics.")
        if out["conflicts"]:
            st._x("UPDATE assertions SET conflicts=? WHERE id=?", (json.dumps(out["conflicts"]), a["id"]))
        return out

    if kind == "scoped_rule":
        if rule_key not in RULE_KEYS:
            raise ValueError(f"rule_key must be one of {sorted(RULE_KEYS)}")
        area_id = eng.resolve_area(area) if area else None
        if not (aid or area_id or well_type):
            raise ValueError("A scoped rule needs a scope: asset_id, area or well_type")
        old, src = eng.rule(rule_key, asset_id=aid, well_type=well_type, equipment_kind=equipment_kind)
        a = st.add_assertion(kind="scoped_rule", asset_id=aid, area_id=area_id,
                             well_type=well_type.upper() if well_type else None, equipment_kind=equipment_kind,
                             rule_key=rule_key, old_value=None if old is None else str(old),
                             new_value=str(float(new_value)), text=text, rationale=rationale, author_user_id=uid,
                             status="applied", conv_id=conv_id)
        eng.refresh(force=True)
        scope = ", ".join(x for x in [f"well type {well_type}" if well_type else "", f"area {area}" if area else "",
                                      aid or "", f"equipment {equipment_kind}" if equipment_kind else ""] if x)
        out["assertion"] = a
        out["consequences"].append(f"Rule {rule_key} = {new_value} now applies to {scope} only "
                                   f"(was {old} from {src['label']}). Other scopes keep the manual's value.")
        return out

    if kind == "well_fact":
        if not aid:
            raise ValueError("asset_id is required")
        latest = eng.latest.loc[aid]
        vf = _ts(valid_from)
        status = "applied"
        claimed = (claimed_state or "").lower()
        evidence = (f"latest inspection {latest.inspection_id} on {fmt_date(latest.t)} by {eng.name(latest.inspector_user_id)}: "
                    f"wellhead {latest.delta_c} °C above air (limit {latest.threshold_c}) → "
                    f"{'producing' if latest.producing else 'not producing'}")
        if vf is not None and vf > latest.t:
            out["checks"].append(f"Planned from {fmt_date(vf)}, after the latest inspection ({fmt_date(latest.t)}): "
                                 "cannot be checked against sensor data yet; recorded as shared context.")
        elif claimed in ("producing", "running", "online", "active"):
            if not latest.producing:
                status = "unconfirmed"
                out["conflicts"].append(f"The data disagrees: {evidence}.")
            else:
                out["checks"].append(f"Consistent with the data: {evidence}.")
        elif claimed in ("not_producing", "down", "shut_in", "stopped", "planned_downtime"):
            if latest.producing:
                status = "unconfirmed"
                out["conflicts"].append(f"The data disagrees: {evidence}.")
            else:
                out["checks"].append(f"Consistent with the data: {evidence}.")
        # who else said something about this well that agrees or disagrees
        for c in eng.context_items(aid):
            out["checks"].append(f"Also on record: {c['id']} by {c['author']} ({c['status']}): \"{c['text']}\"")
        if second_hand_from:
            status = "unconfirmed"
            out["conflicts"].append(f"Second-hand: {user['name']} is relaying what {second_hand_from} said; "
                                    f"recorded as unconfirmed until {second_hand_from} or a work order confirms it.")
        a = st.add_assertion(kind="well_fact", asset_id=aid, text=text, rationale=rationale, author_user_id=uid,
                             valid_from=valid_from or str(eng.as_of.date()), valid_to=valid_to, status=status,
                             conflicts=out["conflicts"], new_value=claimed or None, conv_id=conv_id)
        eng.refresh(force=True)
        out["assertion"] = a
        out["consequences"].append(
            f"Recorded as shared knowledge about {aid} ({a['id']}, status {status}); every user asking about {aid} will see it"
            + ("; marked UNCONFIRMED — ask the author to confirm." if status == "unconfirmed" else "."))
        return out

    raise ValueError(f"Unknown feedback kind '{kind}'")
