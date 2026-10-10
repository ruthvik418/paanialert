"""The Indore replay and the false-alarm cases, through the real cluster rule (no AWS)."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import replay  # noqa: E402


def test_false_alarm_cases_never_reach_alert():
    levels = replay.false_alarm_levels()
    assert set(levels) == {"a", "b", "c"}
    assert all(level != "alert" for level in levels.values()), levels


def test_maintenance_notice_is_what_keeps_case_c_below_alert():
    """Without the notice, case c's 6 homes would be an Alert: the cap is doing the work."""
    from cluster.rule import evaluate

    _, rows = replay.read(replay.FALSE_ALARM_FILE)
    reports = [replay.to_report(r) for r in rows if r["case"] == "c" and r.get("type") != "notice"]
    last = max(replay._parse(r.created_at) for r in reports)
    assert any(c.level == "alert" for c in evaluate(reports, last))


def test_data_files_are_labelled_simulation_and_match_the_generator():
    for path, rows in ((replay.INDORE_FILE, replay.build_indore()), (replay.FALSE_ALARM_FILE, replay.build_false_alarms())):
        header, stored = replay.read(path)
        assert header["label"] == "SIMULATION"
        assert stored == json.loads(json.dumps(rows))          # regenerating gives the same file
        assert all(r.get("simulation") for r in stored if r.get("type") != "notice")


def test_indore_replay_is_reproducible_and_alerts_at_every_adoption_level():
    _, records = replay.read(replay.INDORE_FILE)
    results = [replay.replay(records, a) for a in replay.ADOPTION_LEVELS]
    assert all(r["first_alert"] is not None for r in results)
    assert [r["reports"] for r in results] == [20, 50, 100]
    assert results == [replay.replay(records, a) for a in replay.ADOPTION_LEVELS]
