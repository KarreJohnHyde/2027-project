from app.services import effective_evidence as evidence


def test_same_clock_tick_uses_decision_order_for_effective_view_and_trends(monkeypatch):
    # The older proposal can be approved later; decision order must win.
    amend = {"state": "CORRECTION_APPROVED", "decided_at": "2026-11-13T12:00:00", "decision_id": 7, "review_id": 20,
             "correction": {"action": "AMEND", "corrected_value": 12}}
    remove = {"state": "CORRECTION_APPROVED", "decided_at": "2026-11-13T12:00:00", "decision_id": 8, "review_id": 19,
              "correction": {"action": "REMOVE"}}
    for entries in ([amend, remove], [remove, amend]):
        result = evidence.effective_record({"value": 10}, entries, evidence.MEASUREMENT_FIELDS)
        assert result["correction_state"] == "REMOVED_IN_EFFECTIVE_VIEW"
        assert result["applied_review_id"] == 19
        assert result["original"]["value"] == 10
        monkeypatch.setattr(evidence, "correction_index", lambda *args: ({5: entries}, {}))
        assert evidence.approved_measurement_overrides(None, 1)[5]["removed"] is True


def test_later_timestamp_wins_even_if_id_is_smaller():
    assert evidence.decision_order({"decided_at": "2026-11-14", "decision_id": 1}) > evidence.decision_order({"decided_at": "2026-11-13", "decision_id": 100})
