from app.agents.orchestrator import (
    _attach_commitment_proposal,
    _extract_commitment_proposal,
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
    assert enriched.structured_data["commitment_proposal"]["title"] == (
        "Email the project supervisor"
    )
