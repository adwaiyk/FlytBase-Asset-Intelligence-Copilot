"""Procedure audits on the test dataset (600 wells, today 15 Jan 2027). No model needed."""
import pytest

from copilot import feedback as fb, procedures as P
from copilot.data import load
from copilot.engine import Engine
from copilot.store import Store


@pytest.fixture(scope="module")
def eng(tmp_path_factory):
    d = load(["data/flytbase-dataset/test-data/dataset"])
    s = Store(str(tmp_path_factory.mktemp("p") / "p.db"))
    s.seed_users(d.users, "pw123456")
    return Engine(d, s)


def test_load_and_rules(eng):
    assert str(eng.as_of.date()) == "2027-01-15" and len(eng.d.wells) == 600
    assert eng.rule("producing_delta_c", well_type="T500")[0] == 25  # read from the new T500 manual


def test_gas_odor_deadlines_from_sop(eng):
    rows = P.gas_odor_audit(eng, since="2026-11-01")["rows"]
    assert len(rows) == 26
    assert all(r["deadline_h"] == (12 if "2027" in r["reported_at"] else 24) for r in rows)


def test_bypass_moc_extension(eng):
    rows = {r["asset_id"]: r for r in P.bypass_audit(eng)["rows"]}
    assert rows["WELL-0248"]["status"] == "Allowed" and "MOC-2026-044" in rows["WELL-0248"]["approval"]
    assert rows["WELL-0249"]["status"] == "Expired" and rows["WELL-0405"]["status"] == "Not approved"


def test_recall_and_secondhand_claim(eng):
    rows = P.recalled_pumps(eng)["rows"]
    assert len(rows) == 9 and all(r["lot"] in ("LOT-2409-A", "LOT-2409-C", "LOT-2410-B") for r in rows)
    olivia = eng.store.get_user("U-501")
    out = fb.record(eng, olivia, "well_fact", "Nathan told me the recalled pump on WELL-0577 was swapped",
                    asset_id="WELL-0577", claimed_state="other", second_hand_from="Nathan Pierce")
    assert out["assertion"]["status"] == "unconfirmed"
    r577 = [r for r in P.recalled_pumps(eng)["rows"] if r["asset_id"] == "WELL-0577"][0]
    assert "Olivia Grant" in r577["reported_by_people"]


def test_regulator_letter_soil_samples(eng):
    rows = P.spill_followup_audit(eng, "Northeast Block 7, Northeast Block 8", "2026-06-01", "Soil samples sent to the lab.")["rows"]
    assert len(rows) == 6 and sum(r["compliant"] == "No" for r in rows) == 3


def test_status_precedence_and_delays(eng):
    rows = {r["asset_id"]: r for r in P.status_disagreements(eng)["rows"]}
    assert rows["WELL-0026"]["status_now"] == "Producing oil (unconfirmed)"
    assert rows["WELL-0044"]["status_now"] == "Not producing oil (shut in)"
    d = P.shut_in_delays(eng, "2026")
    assert {r["reason"] for r in d["rows"]} <= {"Parts", "Crews", "Contractors", "Weather"} and len(d["rows"]) >= 20
