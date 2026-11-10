from app.models import Memory, User
from app.services.context.memory_context import build_memory_context, retrieve_relevant_memories


def _user(db, email):
    user = User(email=email, name="Test", password_hash="hashed")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_retrieval_returns_only_relevant_memories_for_owner(db_session):
    owner = _user(db_session, "owner-memory@example.com")
    other = _user(db_session, "other-memory@example.com")
    db_session.add_all([
        Memory(user_id=owner.id, content="I prefer train travel for long journeys", category="travel"),
        Memory(user_id=owner.id, content="I like vegetarian restaurants", category="food"),
        Memory(user_id=other.id, content="I prefer train travel", category="travel"),
    ])
    db_session.commit()

    results = retrieve_relevant_memories(
        db_session, user_id=owner.id, query="Plan my train travel", limit=6
    )

    assert len(results) == 1
    assert results[0].content == "I prefer train travel for long journeys"
    assert all(memory.user_id == owner.id for memory in results)


def test_memory_context_is_empty_when_nothing_matches(db_session):
    user = _user(db_session, "empty-memory@example.com")
    db_session.add(Memory(user_id=user.id, content="I prefer train travel", category="travel"))
    db_session.commit()

    assert build_memory_context(
        db_session, user_id=user.id, query="Write a Python function"
    ) == ""


def test_memory_context_is_bounded_and_labelled(db_session):
    user = _user(db_session, "bounded-memory@example.com")
    db_session.add(Memory(user_id=user.id, content="I prefer train travel", category="travel"))
    db_session.commit()

    context = build_memory_context(
        db_session, user_id=user.id, query="train travel", max_chars=500
    )

    assert context.startswith("USER-SAVED MEMORY")
    assert "I prefer train travel" in context
    assert len(context) <= 500
