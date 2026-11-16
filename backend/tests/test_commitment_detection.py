from app.agents.orchestrator import (
    _attach_commitment_proposal,
    _extract_commitment_proposal,
    _extract_commitment_deadline,
)
from app.schemas.agent import AgentMessageResponse


def test_explicit_first_person_commitment_is_proposed():
    proposal = _extract_commitment_proposal(
        "I'll send Rahul the project report by Friday."
    )
    assert proposal is not None
    assert proposal["type"] == "commitment_proposal"
    assert proposal["title"] == "Send Rahul the project report"


def test_reminder_phrase_can_propose_commitment():
    proposal = _extract_commitment_proposal("Remind me to submit the assignment.")
    assert proposal is not None
    assert proposal["title"] == "Submit the assignment"


def test_general_intention_without_action_is_not_proposed():
    assert _extract_commitment_proposal("I need to understand this topic.") is None
    assert _extract_commitment_proposal("I will think about it.") is None


def test_proposal_is_attached_without_persisting_any_record():
    response = AgentMessageResponse(reply="Sure, I can help.")
    enriched = _attach_commitment_proposal(
        response,
        "I will email the project supervisor.",
    )
    assert enriched.structured_data["type"] == "commitment_proposal"
    assert enriched.structured_data["commitment_proposal"]["title"] == (
        "Email the project supervisor"
    )

from datetime import datetime
from zoneinfo import ZoneInfo


def test_extract_recipient_and_due_date_from_send_commitment():
    proposal = _extract_commitment_proposal(
        "I'll send Rahul the project report by Friday.",
        now=datetime(2026, 11, 16, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
    )
    assert proposal is not None
    assert proposal["title"] == "Send the project report"
    assert proposal["counterparty"] == "Rahul"
    assert proposal["due_at"].startswith("2026-11-20T23:59:00+05:30")
    assert proposal["timezone"] == "Asia/Kolkata"


def test_extract_tomorrow_deadline():
    due_at = _extract_commitment_deadline(
        "I will submit the assignment by tomorrow.",
        now=datetime(2026, 11, 16, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
    )
    assert due_at.startswith("2026-11-17T23:59:00+05:30")


def test_no_deadline_is_not_invented():
    proposal = _extract_commitment_proposal("I will submit the assignment.")
    assert proposal is not None
    assert proposal["due_at"] is None


def test_duplicate_current_user_message_is_not_sent_twice():
    from types import SimpleNamespace
    from app.agents.orchestrator import _build_llm_messages

    conversation = SimpleNamespace(messages=[
        SimpleNamespace(role="user", content="I'll send Rahul the report.")
    ])
    messages = _build_llm_messages(conversation, "I'll send Rahul the report.")
    assert messages == [{"role": "user", "content": "I'll send Rahul the report."}]
