"""Answer questions about uploaded documents with page-aware evidence."""
import logging
import re

from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolContext, ToolResult
from app.agents.llm_provider import get_provider
from app.models.document import Document

logger = logging.getLogger(__name__)

_PAGE_MARKER = re.compile(r"^\[Page (\d+)\]$", re.MULTILINE)
_TOKEN = re.compile(r"[a-z0-9][a-z0-9'-]{2,}")
_STOP_WORDS = {
    "about", "after", "again", "also", "and", "are", "because", "been",
    "before", "being", "between", "both", "could", "does", "during",
    "from", "have", "into", "more", "most", "other", "over", "same",
    "should", "some", "such", "than", "that", "their", "them", "there",
    "these", "they", "this", "those", "through", "under", "very", "what",
    "when", "where", "which", "while", "with", "would", "your",
}


class DocumentQInput(BaseModel):
    document_id: int = Field(...)
    question: str = Field(default="Summarize this document")


def _chunk_text(text: str, size: int = 5000) -> list[str]:
    """Split on paragraph boundaries while retaining page markers."""
    chunks: list[str] = []
    current = ""
    current_page = "Page 1"

    for paragraph in text.split("\n\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        marker = _PAGE_MARKER.fullmatch(paragraph)
        if marker:
            current_page = f"Page {marker.group(1)}"
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if current and len(candidate) > size:
            chunks.append(current.strip())
            # Carry the current page label into the next chunk so citations
            # remain meaningful when a long page spans multiple chunks.
            current = f"[{current_page}]\n\n{paragraph}" if not marker else paragraph
        else:
            current = candidate
    if current.strip():
        chunks.append(current.strip())
    return chunks


def _select_relevant(chunks: list[str], question: str, top_k: int = 4) -> list[str]:
    """Rank chunks by lexical relevance, then return them in document order."""
    query_terms = {
        token for token in _TOKEN.findall(question.lower())
        if token not in _STOP_WORDS
    }
    if not query_terms:
        return chunks[:top_k]

    scored: list[tuple[int, int]] = []
    normalized_question = " ".join(question.lower().split())
    for index, chunk in enumerate(chunks):
        normalized_chunk = chunk.lower()
        terms = _TOKEN.findall(normalized_chunk)
        term_counts = {term: terms.count(term) for term in query_terms}
        score = sum(min(count, 5) for count in term_counts.values())
        if normalized_question and normalized_question in normalized_chunk:
            score += 10
        score += sum(2 for count in term_counts.values() if count)
        scored.append((score, index))

    selected = [index for score, index in scored if score > 0]
    if not selected:
        return chunks[:top_k]
    best = sorted(selected, key=lambda index: (-scored[index][0], index))[:top_k]
    return [chunks[index] for index in sorted(best)]


def _select_summary_chunks(chunks: list[str], top_k: int = 4) -> list[str]:
    """Sample the document from beginning to end for a balanced overview."""
    if len(chunks) <= top_k:
        return chunks
    indexes = [round(i * (len(chunks) - 1) / (top_k - 1)) for i in range(top_k)]
    return [chunks[index] for index in dict.fromkeys(indexes)]


class AnswerDocumentTool(BaseTool):
    name = "answer_document"
    description = "Answer questions about an uploaded PDF, DOCX, TXT, or supported text document using extracted content and page references."
    capability = "document"
    input_schema = DocumentQInput
    requires_confirmation = False
    is_mutating = False

    def execute(self, ctx: ToolContext, params: DocumentQInput) -> ToolResult:
        doc = ctx.db.get(Document, params.document_id)
        if not doc or doc.user_id != ctx.user.id:
            return ToolResult(success=False, message="Document not found or you don't have access.")

        text = doc.text_content or ""
        if not text.strip():
            return ToolResult(success=False, message="This document has no extractable text to search.")

        question = params.question.strip() or "Summarize this document"
        chunks = _chunk_text(text, 5000) if len(text) > 15000 else [text]
        is_summary = any(
            phrase in question.lower()
            for phrase in ("summarize", "summary", "what is this", "overview")
        )

        if len(chunks) > 1:
            selected = (
                _select_summary_chunks(chunks)
                if is_summary
                else _select_relevant(chunks, question)
            )
        else:
            selected = chunks

        context = "\n\n---\n\n".join(selected)
        omitted = max(0, len(chunks) - len(selected))
        coverage_note = (
            f"\n\nRetrieval note: {len(selected)} of {len(chunks)} sections supplied; "
            f"{omitted} sections omitted."
            if omitted else ""
        )

        prompt = f"""You are answering a user's question about an uploaded document.

Document filename: {doc.filename}
Total pages: {doc.page_count}

Evidence extracted from the document:
---
{context}
---
{coverage_note}

User question: {question}

Evidence and citation rules:
- Use ONLY the supplied document evidence. Do not use outside knowledge or guess.
- The source uses explicit markers such as [Page 2]. Cite every factual statement with the page marker(s) that support it, e.g. [Page 2].
- Never invent a page number. If the evidence has no page marker, say that a page reference is unavailable.
- If the answer is not supported by the supplied evidence, say: "I couldn't find this in the retrieved parts of the document." Do not claim the entire document omits it when only selected sections were supplied.
- If the supplied evidence is insufficient, say so clearly and suggest a narrower search question.
- For summaries, distinguish the document's main points from details and note when only selected sections were reviewed.
- Use clear Markdown. Keep quotations short and exact.
"""

        raw = get_provider().generate(prompt)
        if not raw:
            return ToolResult(
                success=False,
                message="The document loaded, but the AI model is unavailable. Check your configured model provider and try again.",
            )

        return ToolResult(
            success=True,
            message=raw.strip(),
            data={
                "type": "document_answer",
                "document_id": doc.id,
                "filename": doc.filename,
                "page_count": doc.page_count,
                "sections_reviewed": len(selected),
                "sections_available": len(chunks),
                "partial_retrieval": omitted > 0,
                "citation_format": "[Page N]",
            },
        )
