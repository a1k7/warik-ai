"""Evidence-based web research: search, fetch and extract public webpages."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
from pydantic import BaseModel, Field

from app.tools.base import BaseTool, ToolContext, ToolResult


class WebResearchInput(BaseModel):
    query: str = Field(..., min_length=3, max_length=500)
    max_pages: int = Field(default=3, ge=1, le=5)


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
                    "title": title[:300],
                    "content": text[:self.MAX_TEXT_CHARS],
                    "truncated": len(text) > self.MAX_TEXT_CHARS,
                    "content_length": len(text),
                }
            finally:
                response.close()

        raise ValueError("Too many webpage redirects.")

    def execute(self, ctx: ToolContext, params: WebResearchInput) -> ToolResult:
        try:
            search_results = DDGS().text(
                params.query,
                max_results=max(params.max_pages * 2, 5),
            )

            if not search_results:
                return ToolResult(
                    success=True,
                    message="Search completed but returned no results.",
                    data={
                        "type": "web_research",
                        "query": params.query,
                        "search_status": "no_results",
                        "sources": [],
                    },
                )

            sources = []
            seen_urls = set()

            for result in search_results:
                url = result.get("href")
                if not url or url in seen_urls:
                    continue

                seen_urls.add(url)

                source = {
                    "title": result.get("title") or "",
                    "search_snippet": result.get("body") or "",
                    "search_url": url,
                    "retrieved": False,
                }

                if len(sources) < params.max_pages:
                    try:
                        fetched = self._fetch_page(url)
                        source.update(fetched)
                    except Exception as exc:
                        source["retrieval_error"] = str(exc)

                sources.append(source)

                if len(sources) >= params.max_pages:
                    break

            retrieved_count = sum(1 for item in sources if item.get("retrieved"))

            return ToolResult(
                success=True,
                message=(
                    f"Found {len(sources)} sources; "
                    f"successfully retrieved {retrieved_count} webpages."
                ),
                data={
                    "type": "web_research",
                    "query": params.query,
                    "search_status": "completed",
                    "source_count": len(sources),
                    "retrieved_count": retrieved_count,
                    "sources": sources,
                },
            )

        except Exception as exc:
            return ToolResult(
                success=False,
                message=f"Web research failed: {type(exc).__name__}: {exc}",
                data={
                    "type": "web_research",
                    "query": params.query,
                    "search_status": "failed",
                    "sources": [],
                },
            )
