from types import SimpleNamespace

from app.services.context.conversation_context import (
    build_conversation_context, extract_task_entities, is_resume_request,
    update_conversation_context,
)


def test_entity_extraction_keeps_only_literal_mentions():
    result = extract_task_entities("Plan a trip to Tokyo for 5 days under ₹45,000 from 12 Nov 2026")
    assert result["location_mention"] == "Tokyo"
    assert result["budget_mention"] == 45000
    assert result["date_mentions"] == ["12 Nov 2026"]


def test_update_merges_state_without_erasing_existing_slots():
    conversation = SimpleNamespace(state_json={"last_location": "Paris", "awaiting": {"slot": "dates"}})
    state = update_conversation_context(conversation, "Make it cheaper")
    assert state["last_location"] == "Paris"
    assert state["awaiting"] == {"slot": "dates"}
    assert state["conversation_context"]["latest_user_message"] == "Make it cheaper"


def test_context_includes_recent_turns_and_active_workflow_bounded():
    conversation = SimpleNamespace(
        state_json={"conversation_context": {"latest_user_message": "Plan Tokyo", "entities": {"location_mention": "Tokyo"}}},
        messages=[SimpleNamespace(role="user", content="Plan Tokyo"), SimpleNamespace(role="assistant", content="How many days?")],
    )
    workflow = SimpleNamespace(id=7, status="IN_PROGRESS", steps_json=[{"id": "s1", "description": "Find attractions", "status": "COMPLETED", "tool": "discover_places"}])
    result = build_conversation_context(conversation, "Make it cheaper", workflow)
    assert "Plan Tokyo" in result
    assert "Make it cheaper" in result
    assert "COMPLETED" in result
    assert len(result) <= 2400


def test_resume_requires_explicit_unambiguous_command():
    assert is_resume_request("continue")
    assert is_resume_request("Please proceed with remaining steps")
    assert not is_resume_request("continue but make it cheaper")
    assert not is_resume_request("yes")
