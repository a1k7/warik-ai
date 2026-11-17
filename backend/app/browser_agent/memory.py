"""Keyword retrieval over small, human-editable markdown preferences."""

import re
from pathlib import Path

from app.browser_agent.runner_paths import MEMORY_DIR


def select_memories(goal: str, limit: int = 3) -> list[dict[str, str]]:
    terms = {word.lower() for word in re.findall(r"[a-zA-Z]{3,}", goal)}
    stop = {"the", "and", "for", "from", "with", "find", "cheapest", "option", "please", "tomorrow"}
    terms -= stop
    ranked = []
    for path in MEMORY_DIR.glob("*.md"):
        content = path.read_text(encoding="utf-8")
        frontmatter = content.split("---", 2)[1] if content.startswith("---") else ""
        keywords = set(re.findall(r"[a-zA-Z]{3,}", frontmatter.lower()))
        body = set(re.findall(r"[a-zA-Z]{3,}", content.lower()))
        score = len(terms & (keywords | body))
        if score:
            ranked.append((score, path.name, content[:5000]))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [{"file": name, "content": content} for _, name, content in ranked[:limit]]
