"""Bounded, user-scoped retrieval of explicit memories for agent planning."""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models import Memory

# Keep retrieval explainable and avoid ranking on common conversational words.
_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "cheaper",
    "could", "do", "for", "from", "get", "give", "good", "help", "i",
    "in", "is", "it", "make", "me", "my", "of", "on", "or", "please",
    "show", "that", "the", "this", "to", "want", "with", "you", "your",
}


def _terms(value: str) -> set[str]:
    return {
        token for token in re.findall(r"[a-zA-Z0-9]{2,}", (value or "").lower())
        if token not in _STOP_WORDS
    }


def retrieve_relevant_memories(
    db: Session,
    *,
    user_id: int,
    query: str,
    limit: int = 6,
) -> list[Memory]:
    """Return only explicit memories with lexical relevance to this request.

    The user_id predicate is mandatory; no memory from another account can
    enter the planner context. A small result limit bounds prompt exposure.
    """
    query_terms = _terms(query)
    if not query_terms or limit <= 0:
        return []

    candidates = (
        db.query(Memory)
        .filter(Memory.user_id == user_id)
        .order_by(Memory.updated_at.desc(), Memory.id.desc())
        .limit(100)
        .all()
    )

    ranked: list[tuple[int, float, Memory]] = []
    for memory in candidates:
        memory_terms = _terms(f"{memory.content} {memory.category or ''}")
        overlap = query_terms & memory_terms
        if not overlap:
            continue
        # Prefer memories that cover more of the request; category matches add
        # a small tie-breaker but never make an unrelated memory relevant.
        score = len(overlap) / max(1, len(query_terms))
        ranked.append((len(overlap), score, memory))

    ranked.sort(key=lambda item: (item[0], item[1], item[2].updated_at, item[2].id), reverse=True)
    return [item[2] for item in ranked[:limit]]


def build_memory_context(
    db: Session,
    *,
    user_id: int,
    query: str,
    limit: int = 6,
    max_chars: int = 1800,
) -> str:
    """Format relevant saved facts as clearly labelled, bounded context."""
    memories = retrieve_relevant_memories(
        db, user_id=user_id, query=query, limit=limit
    )
    if not memories:
        return ""

    lines = ["USER-SAVED MEMORY (use only when relevant; latest request overrides):"]
    used = len(lines[0])
    for memory in memories:
        category = f" [{memory.category}]" if memory.category else ""
        line = f"- {memory.content.strip()[:400]}{category}"
        if used + len(line) + 1 > max_chars:
            break
        lines.append(line)
        used += len(line) + 1
    return "\n".join(lines) if len(lines) > 1 else ""
