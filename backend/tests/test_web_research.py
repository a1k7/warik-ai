from app.tools.web_research import WebResearchTool


def test_relevance_ranking_prefers_matching_title():
    query = "latest Python programming language release"

    strong = {
        "title": "Python latest release information",
        "body": "Official release notes and downloads",
    }
    weak = {
        "title": "A general programming tutorial",
        "body": "Learn programming concepts",
    }

    assert WebResearchTool._relevance_score(query, strong) > (
        WebResearchTool._relevance_score(query, weak)
    )


def test_canonical_url_removes_fragment_and_trailing_slash():
    first = "https://example.com/article/#section"
    second = "https://example.com/article/"

    assert WebResearchTool._canonical_url(first) == (
        WebResearchTool._canonical_url(second)
    )


def test_duplicate_candidates_are_removed_and_best_pages_are_fetched(monkeypatch):
    import app.tools.web_research as module
    from app.tools.web_research import WebResearchInput
    from app.tools.base import ToolContext

    class FakeDDGS:
        def text(self, query, max_results):
            assert max_results >= 16
            return [
                {
                    "title": "General programming article",
                    "body": "A broad introduction",
                    "href": "https://example.com/general",
                },
                {
                    "title": "Python latest release",
                    "body": "Release details and documentation",
                    "href": "https://python.org/releases",
                },
                {
                    "title": "Duplicate Python latest release",
                    "body": "Release details",
                    "href": "https://python.org/releases/#top",
                },
            ]

    monkeypatch.setattr(module, "DDGS", FakeDDGS)

    tool = WebResearchTool()
    fetched = []

    def fake_fetch(url):
        fetched.append(url)
        return {
            "retrieved": True,
            "url": url,
            "retrieved_at": "2026-11-18T00:00:00+00:00",
            "title": "Retrieved page",
            "content": "Actual retrieved page content",
        }

    monkeypatch.setattr(tool, "_fetch_page", fake_fetch)

    result = tool.execute(
        ToolContext(db=None, user=None),
        WebResearchInput(
            query="Python latest release",
            max_pages=2,
        ),
    )

    assert result.success is True
    assert result.data["candidate_count"] == 2
    assert result.data["retrieved_count"] == 2
    assert fetched[0] == "https://python.org/releases"


def test_multi_query_search_merges_and_deduplicates_results(monkeypatch):
    import app.tools.web_research as module
    from app.tools.web_research import WebResearchInput
    from app.tools.base import ToolContext

    calls = []

    class FakeDDGS:
        def text(self, query, max_results):
            calls.append(query)
            if query == "Python release":
                return [
                    {
                        "title": "Python release notes",
                        "body": "Latest Python release information",
                        "href": "https://python.org/releases/",
                    }
                ]
            return [
                {
                    "title": "Python official documentation",
                    "body": "Python documentation and release information",
                    "href": "https://python.org/releases/#latest",
                },
                {
                    "title": "Python downloads",
                    "body": "Download Python",
                    "href": "https://python.org/downloads/",
                },
            ]

    monkeypatch.setattr(module, "DDGS", FakeDDGS)

    tool = WebResearchTool()
    fetched = []

    def fake_fetch(url):
        fetched.append(url)
        return {
            "retrieved": True,
            "url": url,
            "retrieved_at": "2026-11-18T00:00:00+00:00",
            "title": "Retrieved",
            "content": "Retrieved evidence",
        }

    monkeypatch.setattr(tool, "_fetch_page", fake_fetch)

    result = tool.execute(
        ToolContext(db=None, user=None),
        WebResearchInput(
            query="Python release",
            queries=["Python official documentation"],
            max_pages=3,
        ),
    )

    assert result.success is True
    assert calls == ["Python release", "Python official documentation"]
    assert result.data["candidate_count"] == 2
    assert result.data["retrieved_count"] == 2
    assert len({item["canonical_url"] for item in result.data["sources"]}) == 2
    assert any(
        len(item["matched_queries"]) == 2
        for item in result.data["sources"]
    )
