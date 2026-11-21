"""Evidence-based web research: search, fetch and extract public webpages."""

from __future__ import annotations

import ipaddress
import re
import socket
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolContext, ToolResult


class WebResearchInput(BaseModel):
    query: str = Field(..., min_length=3, max_length=500)
    max_pages: int = Field(default=5, ge=1, le=8)
    queries: list[str] = Field(default_factory=list, max_length=4)


class WebResearchTool(BaseTool):
    name = "web_research"
    description = (
        "Research current information on the public web. Searches for sources, "
        "retrieves webpages, extracts readable content and returns evidence "
        "with source URLs. Use for latest information and website research."
    )
    capability = "research"
    input_schema = WebResearchInput
    requires_confirmation = False
    is_mutating = False

    USER_AGENT = "Mozilla/5.0 (compatible; WarikAI/1.0)"
    MAX_BYTES = 2_000_000
    MAX_TEXT_CHARS = 12_000
    MAX_REDIRECTS = 4

    @staticmethod
    def _validate_public_url(url: str) -> str:
        parsed = urlparse(url)

        if parsed.scheme not in {"http", "https"}:
            raise ValueError("Only HTTP and HTTPS URLs are supported.")

        if not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Invalid webpage URL.")

        host = parsed.hostname.lower()
        if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
            raise ValueError("Local network URLs are not allowed.")

        try:
            addresses = {
                item[4][0]
                for item in socket.getaddrinfo(host, None)
            }
        except socket.gaierror as exc:
            raise ValueError("Could not resolve the webpage hostname.") from exc

        if not addresses:
            raise ValueError("The webpage hostname has no resolved address.")

        for address in addresses:
            ip = ipaddress.ip_address(address)
            if (
                not ip.is_global
                or ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
            ):
                raise ValueError("Private or non-public network addresses are not allowed.")

        return url

    def _fetch_page(self, initial_url: str) -> dict:
        current_url = initial_url

        for _ in range(self.MAX_REDIRECTS + 1):
            self._validate_public_url(current_url)

            response = requests.get(
                current_url,
                headers={"User-Agent": self.USER_AGENT},
                timeout=(5, 15),
                stream=True,
                allow_redirects=False,
            )

            try:
                if response.is_redirect or response.is_permanent_redirect:
                    location = response.headers.get("Location")
                    if not location:
                        raise ValueError("Redirect did not include a destination.")
                    current_url = urljoin(current_url, location)
                    continue

                response.raise_for_status()

                content_type = response.headers.get("Content-Type", "").lower()
                if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                    return {
                        "retrieved": False,
                        "url": current_url,
                        "error": f"Unsupported content type: {content_type or 'unknown'}",
                    }

                chunks = []
                total = 0

                for chunk in response.iter_content(chunk_size=16_384):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > self.MAX_BYTES:
                        raise ValueError("Webpage exceeded the 2 MB retrieval limit.")
                    chunks.append(chunk)

                html = b"".join(chunks)
                soup = BeautifulSoup(html, "lxml")

                for tag in soup([
                    "script", "style", "noscript", "svg", "nav",
                    "footer", "header", "aside", "form"
                ]):
                    tag.decompose()

                title = soup.title.get_text(" ", strip=True) if soup.title else ""
                main = soup.find("main") or soup.find("article") or soup.body or soup
                text = " ".join(main.stripped_strings)

                return {
                    "retrieved": True,
                    "url": response.url,
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "title": title[:300],
                    "content": text[:self.MAX_TEXT_CHARS],
                    "truncated": len(text) > self.MAX_TEXT_CHARS,
                    "content_length": len(text),
                }
            finally:
                response.close()

        raise ValueError("Too many webpage redirects.")

    @staticmethod
    def _tokens(value: str) -> set[str]:
        stopwords = {
            "the", "a", "an", "and", "or", "but", "for", "to", "of",
            "in", "on", "at", "by", "with", "from", "is", "are", "was",
            "were", "what", "when", "where", "who", "why", "how", "which",
            "about", "please", "find", "search", "latest", "best",
        }
        words = re.findall(r"[a-z0-9]+", (value or "").lower())
        return {word for word in words if len(word) > 1 and word not in stopwords}

    @classmethod
    def _relevance_score(cls, query: str, result: dict) -> float:
        query_tokens = cls._tokens(query)
        if not query_tokens:
            return 0.0

        title_tokens = cls._tokens(result.get("title", ""))
        snippet_tokens = cls._tokens(result.get("body", ""))

        title_matches = len(query_tokens & title_tokens)
        snippet_matches = len(query_tokens & snippet_tokens)
        coverage = len(query_tokens & (title_tokens | snippet_tokens)) / len(query_tokens)

        title_ratio = title_matches / len(query_tokens)
        snippet_ratio = snippet_matches / len(query_tokens)

        phrase = " ".join(query.lower().split())
        title = (result.get("title") or "").lower()
        snippet = (result.get("body") or "").lower()
        phrase_bonus = 0.5 if phrase and (phrase in title or phrase in snippet) else 0.0

        return round(
            (title_ratio * 3.0) + snippet_ratio + coverage + phrase_bonus,
            4,
        )

    @staticmethod
    def _canonical_url(url: str) -> str:
        parsed = urlparse(url)
        return parsed._replace(fragment="").geturl().rstrip("/").lower()

    @staticmethod
    def _source_category(url: str) -> str:
        """Describe observable domain characteristics, not source trust."""
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        path = (parsed.path or "").lower()

        if host.endswith(".gov") or ".gov." in host:
            return "government_domain"
        if host.endswith(".edu") or ".edu." in host:
            return "educational_domain"
        if any(token in path for token in ("/docs", "/documentation", "/reference")):
            return "documentation_path"
        return "general_web"

    def execute(self, ctx: ToolContext, params: WebResearchInput) -> ToolResult:
        try:
            # The original request always remains the primary ranking objective.
            search_queries = [params.query]
            for query in params.queries:
                cleaned = query.strip()
                if cleaned and cleaned.casefold() not in {
                    item.casefold() for item in search_queries
                }:
                    search_queries.append(cleaned)

            # Bound search fan-out to control latency and provider load.
            search_queries = search_queries[:5]
            candidate_limit = min(max(params.max_pages * 8, 16), 40)

            candidates_by_url = {}
            query_errors = []

            for search_query in search_queries:
                try:
                    results = list(
                        DDGS().text(search_query, max_results=candidate_limit) or []
                    )
                except Exception as exc:
                    query_errors.append({
                        "query": search_query,
                        "error": f"{type(exc).__name__}: {str(exc)[:200]}",
                    })
                    continue

                for result in results:
                    url = result.get("href")
                    if not url:
                        continue

                    try:
                        canonical = self._canonical_url(url)
                    except Exception:
                        continue

                    if not canonical:
                        continue

                    score = self._relevance_score(params.query, result)
                    existing = candidates_by_url.get(canonical)

                    if existing is None:
                        candidates_by_url[canonical] = {
                            "title": result.get("title") or "",
                            "search_snippet": result.get("body") or "",
                            "search_url": url,
                            "canonical_url": canonical,
                            "relevance_score": score,
                            "matched_queries": [search_query],
                        }
                    else:
                        if search_query not in existing["matched_queries"]:
                            existing["matched_queries"].append(search_query)

                        if score > existing["relevance_score"]:
                            existing["title"] = result.get("title") or existing["title"]
                            existing["search_snippet"] = (
                                result.get("body") or existing["search_snippet"]
                            )
                            existing["search_url"] = url
                            existing["relevance_score"] = score

            candidates = list(candidates_by_url.values())
            candidates.sort(
                key=lambda item: (
                    item["relevance_score"],
                    len(item["matched_queries"]),
                ),
                reverse=True,
            )

            if not candidates:
                return ToolResult(
                    success=bool(query_errors) is False,
                    message=(
                        "All web searches failed."
                        if query_errors
                        else "Search completed but returned no usable results."
                    ),
                    data={
                        "type": "web_research",
                        "query": params.query,
                        "search_queries": search_queries,
                        "search_status": "failed" if query_errors else "no_results",
                        "query_errors": query_errors,
                        "candidate_count": 0,
                        "retrieved_count": 0,
                        "sources": [],
                    },
                )

            sources = []
            for rank, candidate in enumerate(candidates[:params.max_pages], start=1):
                source = {
                    **candidate,
                    "rank": rank,
                    "domain": urlparse(candidate["search_url"]).hostname,
                    "source_category": self._source_category(candidate["search_url"]),
                    "retrieved": False,
                }

                try:
                    fetched = self._fetch_page(candidate["search_url"])
                    source.update(fetched)
                except Exception as exc:
                    source["retrieval_error"] = (
                        f"{type(exc).__name__}: {str(exc)[:300]}"
                    )

                sources.append(source)

            retrieved_count = sum(
                1 for item in sources
                if item.get("retrieved") is True and item.get("content")
            )

            return ToolResult(
                success=True,
                message=(
                    f"Searched {len(search_queries)} query angles; "
                    f"ranked {len(candidates)} unique candidates and "
                    f"retrieved {retrieved_count} of {len(sources)} selected pages."
                ),
                data={
                    "type": "web_research",
                    "query": params.query,
                    "search_queries": search_queries,
                    "search_status": "completed",
                    "query_errors": query_errors,
                    "candidate_count": len(candidates),
                    "selected_count": len(sources),
                    "retrieved_count": retrieved_count,
                    "sources": sources,
                },
            )

        except Exception as exc:
            return ToolResult(
                success=False,
                message=f"Web research failed: {type(exc).__name__}: {str(exc)[:300]}",
                data={
                    "type": "web_research",
                    "query": params.query,
                    "search_status": "failed",
                    "sources": [],
                },
            )
