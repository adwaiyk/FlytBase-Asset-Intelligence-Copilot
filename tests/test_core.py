"""Core tests without a model: deterministic engine vs the expected example answers,
auth + privacy, and the agent loop driven by a scripted fake LLM.

Run: python -m pytest -q tests   (needs the dataset at data/flytbase-dataset)
"""
import pytest

from copilot import feedback as fb
from copilot.agent import Agent
from copilot.data import load
from copilot.engine import Engine
from copilot.store import Store


@pytest.fixture(scope="module")
def data():
    return load()


@pytest.fixture()
def env(data, tmp_path):
    s = Store(str(tmp_path / "t.db"))
    s.seed_users(data.users, "pw123456")
    return data, s, Engine(data, s)


def test_as_of_and_rules(data):
    assert str(data.as_of.date()) == "2026-10-16"
    r = {(x.key, x.scope.get("well_type")): x.value for x in data.rules}
    assert r[("producing_delta_c", "T200")] == 15 and r[("producing_delta_c", "T350")] == 20
    assert r[("rca_corrective_count", "T350")] == 3  # inherited from T200


def test_q1_q2_q3(env):
    _, _, e = env
    s = e.well_snapshot("WELL-0001")["rows"][0]
    assert not s["producing"] and s["delta_c"] == 3.2 and s["inspector"] == "Ryan Brooks"
    assert "CTX-0001-003" in s["reason"] and s["recorded_status_out_of_date"]
    rows = e.fleet_status(area="Northeast Block 8", producing=False)["rows"]
    assert sorted(r["asset_id"] for r in rows) == ["WELL-0164", "WELL-0170", "WELL-0172", "WELL-0175"]
    ts = e.timeseries("WELL-0001", "last_13_weeks")["rows"]
    assert len(ts) == 13 and [r["date"] for r in ts if not r["producing"]] == ["8 Oct 2026", "15 Oct 2026"]


def test_q4_to_q11(env):
    _, _, e = env
    sp = e.spills(asset_ids=["WELL-0001"])["rows"]
    assert len(sp) == 6 and round(sum(r["volume_bbl"] for r in sp), 1) == 15.1
    assert e.downtime(asset_ids=["WELL-0001"], period="2025")["summary"].count("21 days") == 1
    top = e.downtime(area="Northeast Block 7", period="last_4_months", top_n=3)["rows"]
    assert {(r["asset_id"], r["downtime_days"]) for r in top} == {("WELL-0121", 49), ("WELL-0138", 42), ("WELL-0107", 42)}
    q7 = e.spills(area="Northeast Block 8", period="last_90_days")["rows"]
    assert sorted(r["asset_id"] for r in q7) == ["WELL-0151", "WELL-0165", "WELL-0175", "WELL-0186"]
    hm = {r["area"]: r["Total"] for r in e.spills(period="2026", group_by="area_month")["rows"]}
    assert hm == {"Northeast Block 7": 37, "Northeast Block 8": 26, "Southwest Block 23": 35, "Southwest Block 24": 43}
    br = [(r["protocol"], r["status"]) for r in e.compliance_audit(asset_id="WELL-0001")["rows"] if r["status"] == "breach"]
    assert sorted(p for p, _ in br) == ["RC-04", "SR-01", "SR-02", "SR-03"]
    q10 = e.compliance_audit(area="Southwest Block 24", period="last_90_days", protocol="SR-02", status="breach")["rows"]
    assert sorted(r["asset_id"] for r in q10) == ["WELL-0082", "WELL-0100"]
    cost = {r["asset_id"]: r["cost_usd"] for r in e.repairs(asset_ids=["WELL-0121", "WELL-0138", "WELL-0107"])["rows"]}
    assert cost == {"WELL-0121": 25794, "WELL-0138": 46942, "WELL-0107": 5176}


def test_feedback_scopes(env):
    _, s, e = env
    mt = s.get_user("U-201")
    out = fb.record(e, mt, "correct_reading", "re-measured 41.0", asset_id="WELL-0164", date="2026-10-15",
                    field="wellhead_temp_c", new_value=41.0)
    assert out["conflicts"] and e.well_snapshot("WELL-0164")["rows"][0]["producing"]
    assert len(e.fleet_status(area="NE-08", producing=False)["rows"]) == 3
    fb.record(e, mt, "correct_spill_volume", "5.4 measured", asset_id="WELL-0151", date="2026-09-24", new_value=5.4)
    q15 = e.compliance_audit(area="NE-08", period="last_90_days", protocol="SR-01")["rows"]
    assert [r["asset_id"] for r in q15] == ["WELL-0151"] and q15[0]["status"] == "breach"
    before = {r["asset_id"] for r in e.rca_candidates(area="NE-07", equipment_kind="pump_jack")["rows"]}
    fb.record(e, mt, "scoped_rule", "T350 after 2", rule_key="rca_corrective_count", well_type="T350",
              equipment_kind="pump_jack", new_value=2)
    after = {r["asset_id"] for r in e.rca_candidates(area="NE-07", equipment_kind="pump_jack")["rows"]}
    assert before == {"WELL-0108", "WELL-0121", "WELL-0138"} and after == before | {"WELL-0120"}
    tyler = s.get_user("U-204")
    assert fb.record(e, tyler, "well_fact", "running fine", asset_id="WELL-0175",
                     claimed_state="producing")["assertion"]["status"] == "unconfirmed"


def test_auth_and_privacy(env):
    _, s, _ = env
    assert s.login("U-201", "wrong") is None
    tok = s.login("U-201", "pw123456")
    assert s.user_for_token(tok)["name"] == "Michael Turner"
    c = s.new_conversation("U-201", "2026-10-16")
    s.add_message("U-201", c, "user", "hello")
    assert s.messages("U-202", c) == []
    with pytest.raises(PermissionError):
        s.add_message("U-202", c, "user", "sneaky")


class FakeLLM:
    """Plays back scripted turns: each item is a list of tool calls or a final text."""
    def __init__(self, script):
        self.script, self.last_model, self.calls = list(script), "fake", 0

    def chat(self, messages, tools=None, temperature=0.1):
        step = self.script.pop(0)
        if isinstance(step, str):
            return {"content": step, "tool_calls": [], "model": "fake"}
        return {"content": "", "tool_calls": [{"id": f"c{i}", "name": n, "arguments": a} for i, (n, a) in enumerate(step)],
                "model": "fake"}


def test_agent_loop_memory_and_visual(env):
    _, s, e = env
    mt, jr = s.get_user("U-201"), s.get_user("U-202")
    day1 = s.conversation("U-201", s.new_conversation("U-201", "2026-10-16"))
    ag = Agent(e, FakeLLM([[("downtime", {"area": "Northeast Block 7", "period": "last_4_months", "top_n": 3})],
                           "**WELL-0121, WELL-0138 and WELL-0107** had the most downtime."]))
    out = ag.run(mt, day1, "Which 3 wells in Northeast Block 7 had the most downtime in the last 4 months? Show a bar chart.")
    assert out["visual"]["component"] == "bar_chart" and len(out["visual"]["rows"]) == 3
    day2 = s.conversation("U-201", s.new_conversation("U-201", "2026-10-17"))
    ag.llm = FakeLLM([[("recall_my_conversations", {"when": "yesterday"})], "ok"])
    ag.run(mt, day2, "For the three wells we discussed yesterday, what have repairs cost this year?")
    assert "WELL-0107" in ag.recall(mt, day2, "yesterday")["summary"]
    jc = s.conversation("U-202", s.new_conversation("U-202", "2026-10-17"))
    assert "No earlier conversations" in ag.recall(jr, jc, "yesterday")["summary"]
