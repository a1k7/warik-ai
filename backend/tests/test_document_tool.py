from types import SimpleNamespace

from app.tools import document_tool


def test_page_numbers_only_include_explicit_source_markers():
    text = "[Page 1]\n\nIntro\n\n[Page 3]\n\nImplementation details"
    assert document_tool._page_numbers(text) == {1, 3}


def test_invalid_model_page_citations_are_replaced():
    answer = "The policy is defined here [Page 3]. Another claim [Page 9]."
    result = document_tool._validate_page_citations(answer, {1, 3})
    assert "[Page 3]" in result
    assert "[Page 9]" not in result
    assert "[page reference unavailable in retrieved evidence]" in result


def test_relevant_retrieval_does_not_fallback_to_unrelated_first_chunk():
    chunks = [
        "[Page 1]\n\nIntroduction to the project.",
        "[Page 7]\n\nRSA signature verification and tamper detection.",
    ]
    selected = document_tool._select_relevant(
        chunks,
        "Explain RSA signature verification",
    )
    assert selected == [chunks[1]]


def test_retrieval_preserves_page_markers_across_chunks():
    text = (
        "[Page 1]\n\n" + ("Intro material. " * 250)
        + "\n\n[Page 2]\n\n" + ("RSA verification material. " * 250)
    )
    chunks = document_tool._chunk_text(text, size=1000)
    assert len(chunks) > 2
    assert any("[Page 1]" in chunk for chunk in chunks)
    assert any("[Page 2]" in chunk for chunk in chunks)


def test_document_answer_prompt_requires_component_grounding(monkeypatch):
    doc = SimpleNamespace(
        id=12,
        user_id=7,
        filename="architecture.pdf",
        page_count=2,
        text_content=(
            "[Page 1]\n\nPolicy engine evaluates YAML rules.\n\n"
            "[Page 2]\n\ncrypto.py implements RSA signing and verification."
        ),
    )
    captured = {}

    class FakeProvider:
        def generate(self, prompt):
            captured["prompt"] = prompt
            return "The crypto module signs receipts [Page 2]."

    monkeypatch.setattr(document_tool, "get_provider", lambda: FakeProvider())
    ctx = SimpleNamespace(
        db=SimpleNamespace(get=lambda model, document_id: doc),
        user=SimpleNamespace(id=7),
    )
    params = document_tool.DocumentQInput(
        document_id=12,
        question="Explain signing",
    )

    result = document_tool.AnswerDocumentTool().execute(ctx, params)

    assert result.success is True
    assert result.message.endswith("[Page 2].")
    assert "Do not assign an operation to a software component" in captured["prompt"]
    assert "Do not claim that the system blocks, allows, executes" in captured["prompt"]
    assert result.data["retrieved_pages"] == [1, 2]


def test_document_access_is_scoped_to_owner():
    doc = SimpleNamespace(id=12, user_id=8, text_content="secret")
    ctx = SimpleNamespace(
        db=SimpleNamespace(get=lambda model, document_id: doc),
        user=SimpleNamespace(id=7),
    )
    params = document_tool.DocumentQInput(document_id=12, question="What is this?")
    result = document_tool.AnswerDocumentTool().execute(ctx, params)
    assert result.success is False
    assert "don't have access" in result.message
