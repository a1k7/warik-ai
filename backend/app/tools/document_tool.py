"""Answer questions about uploaded documents using Ollama."""
import logging
from pydantic import BaseModel, Field
from app.tools.base import BaseTool, ToolContext, ToolResult
from app.agents.llm_provider import get_provider
from app.models.document import Document

logger = logging.getLogger(__name__)


class DocumentQInput(BaseModel):
    document_id: int = Field(...)
    question: str = Field(default="Summarize this document")


def _chunk_text(text: str, size: int = 5000) -> list[str]:
    chunks = []
    paragraphs = text.split("\n\n")
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 > size and current:
            chunks.append(current.strip())
            current = para
        else:
            current = current + "\n\n" + para if current else para
    if current.strip():
        chunks.append(current.strip())
    return chunks


def _select_relevant(chunks: list[str], question: str, top_k: int = 3) -> list[str]:
    q_words = set(w.lower() for w in question.split() if len(w) > 3)

    def score(chunk: str) -> int:
        c_lower = chunk.lower()
        return sum(c_lower.count(w) for w in q_words)

    ranked = sorted(enumerate(chunks), key=lambda x: score(x[1]), reverse=True)
    selected = [chunks[i] for i, _ in ranked[:top_k]]
    return selected or chunks[:top_k]


class AnswerDocumentTool(BaseTool):
    name = "answer_document"
    description = "Answer a question about an uploaded document (PDF, DOCX, TXT). Use this when the user references a document they've uploaded."
    capability = "document"
    input_schema = DocumentQInput
    requires_confirmation = False
    is_mutating = False

    def execute(self, ctx: ToolContext, params: DocumentQInput) -> ToolResult:
        doc = ctx.db.get(Document, params.document_id)
        if not doc or doc.user_id != ctx.user.id:
            return ToolResult(success=False, message="Document not found or you don't have access.")

        text = doc.text_content
        question = params.question.strip() or "Summarize this document"

        # Chunk if needed
        if len(text) > 15000:
            chunks = _chunk_text(text, 5000)
            is_summary = any(k in question.lower() for k in ("summarize", "summary", "what is this", "overview"))
            if is_summary:
                selected = chunks[:3]
                context = "\n\n---\n\n".join(selected)
                truncation_note = f"\n(Note: Document has {len(chunks)} sections; summarizing first 3.)"
            else:
                selected = _select_relevant(chunks, question, top_k=3)
                context = "\n\n---\n\n".join(selected)
                truncation_note = f"\n(Showing 3 of {len(chunks)} most relevant sections.)"
        else:
            context = text
            truncation_note = ""

        prompt = f"""You are analyzing a document.

Filename: {doc.filename}
Total pages: {doc.page_count}

Document content:
---
{context}
---{truncation_note}

User's question: {question}

Instructions:
- Answer using ONLY the content above.
- If the answer isn't in the content, say: "This document doesn't mention that."
- Be clear and well-structured with markdown (headings, bullets, tables where relevant).
- If summarizing, cover: main topic, key points, and important details.
- Quote short excerpts when they strengthen the answer.
"""

        raw = get_provider().generate(prompt)
        if not raw:
            return ToolResult(
                success=False,
                message="The document loaded, but my AI model is unavailable. Please make sure Ollama is running and try again.",
            )

        return ToolResult(
            success=True,
            message=raw.strip(),
            data={
                "type": "document_answer",
                "document_id": doc.id,
                "filename": doc.filename,
                "page_count": doc.page_count,
            },
        )