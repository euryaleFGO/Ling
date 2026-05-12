# -*- coding: utf-8 -*-
"""
Web search tool using DuckDuckGo.

Lightweight alternative to BrowserSearchTool — no browser dependency.
Uses duckduckgo-search package for search and requests for page fetching.
"""

from __future__ import annotations

import logging
import re
from typing import List

from .base_tool import BaseTool, ToolParameter, ToolResult

logger = logging.getLogger(__name__)


class WebSearchTool(BaseTool):
    """Web search tool using DuckDuckGo — no API key, no browser needed."""

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return (
            "在互联网上检索信息。仅当用户明确要「上网搜索、查新闻/资料、百度一下」等时使用；"
            "支持 action: search（返回结果列表）、read_url（抓取网页正文）、deep_search（搜索并读多条摘要）。"
            "严禁用于：打开摄像头、拍照、截图、截屏、照相——那些应使用 camera_capture 或 screenshot_analyze。"
        )

    @property
    def parameters(self) -> List[ToolParameter]:
        return [
            ToolParameter(
                name="action",
                type="string",
                description="Action: search, read_url, or deep_search",
                required=True,
                enum=["search", "read_url", "deep_search"],
            ),
            ToolParameter(
                name="query",
                type="string",
                description="Search query (required for search and deep_search)",
                required=False,
            ),
            ToolParameter(
                name="url",
                type="string",
                description="URL to read (required for read_url)",
                required=False,
            ),
            ToolParameter(
                name="max_results",
                type="integer",
                description="Maximum number of results (default 5, max 10)",
                required=False,
            ),
        ]

    def execute(
        self,
        action: str,
        query: str = None,
        url: str = None,
        max_results: int = 5,
        **kwargs,
    ) -> ToolResult:
        try:
            if action == "search":
                return self._search(query, max_results)
            elif action == "read_url":
                return self._read_url(url)
            elif action == "deep_search":
                return self._deep_search(query, max_results)
            else:
                return ToolResult(success=False, error=f"Unknown action: {action}")
        except Exception as e:
            logger.error(f"[WebSearch] error: {e}", exc_info=True)
            return ToolResult(success=False, error=str(e))

    def _search(self, query: str, max_results: int = 5) -> ToolResult:
        if not query or not query.strip():
            return ToolResult(success=False, error="query is required for search")

        max_results = min(max(1, max_results), 10)

        try:
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS
        except ImportError:
            return ToolResult(
                success=False,
                error="ddgs not installed. Run: pip install ddgs",
            )

        try:
            with DDGS() as ddgs:
                raw_results = list(ddgs.text(query.strip(), max_results=max_results))
        except Exception as e:
            logger.warning(f"[WebSearch] DDGS search failed: {e}")
            return ToolResult(
                success=False,
                error=f"Search failed: {e}",
            )

        results = []
        for r in raw_results:
            results.append({
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
            })

        return ToolResult(
            success=True,
            data={
                "query": query,
                "count": len(results),
                "results": results,
            },
        )

    def _read_url(self, url: str) -> ToolResult:
        if not url or not url.strip():
            return ToolResult(success=False, error="url is required for read_url")

        try:
            import requests
        except ImportError:
            return ToolResult(success=False, error="requests not installed")

        try:
            resp = requests.get(
                url.strip(),
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    )
                },
                timeout=15,
            )
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            html = resp.text
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to fetch URL: {e}")

        # Extract text from HTML
        text = self._html_to_text(html)

        # Truncate to reasonable size
        max_chars = 8000
        if len(text) > max_chars:
            text = text[:max_chars] + "\n... (truncated)"

        return ToolResult(
            success=True,
            data={
                "url": url,
                "title": self._extract_title(html),
                "content_length": len(text),
                "content": text,
            },
        )

    def _deep_search(self, query: str, max_results: int = 3) -> ToolResult:
        if not query or not query.strip():
            return ToolResult(success=False, error="query is required for deep_search")

        max_results = min(max(1, max_results), 5)

        # First search
        search_result = self._search(query, max_results)
        if not search_result.success:
            return search_result

        results = search_result.data["results"]

        # Fetch content for each result
        for r in results:
            try:
                url = r.get("url", "")
                if not url:
                    continue
                content_result = self._read_url(url)
                if content_result.success:
                    r["content"] = content_result.data.get("content", "")[:3000]
                else:
                    r["content"] = ""
            except Exception:
                r["content"] = ""

        return ToolResult(
            success=True,
            data={
                "query": query,
                "count": len(results),
                "results": results,
            },
        )

    @staticmethod
    def _html_to_text(html: str) -> str:
        """Convert HTML to readable text. Uses regex — no lxml dependency."""
        # Remove script and style elements
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        # Remove HTML comments
        text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
        # Replace common block elements with newlines
        text = re.sub(r"<(?:br|hr|p|div|h[1-6]|li|tr)[^>]*/?>", "\n", text, flags=re.IGNORECASE)
        # Remove remaining tags
        text = re.sub(r"<[^>]+>", "", text)
        # Decode HTML entities
        text = text.replace("&amp;", "&")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&quot;", '"')
        text = text.replace("&nbsp;", " ")
        text = re.sub(r"&#?\w+;", "", text)
        # Collapse whitespace
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _extract_title(html: str) -> str:
        """Extract <title> from HTML."""
        m = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.DOTALL | re.IGNORECASE)
        return m.group(1).strip() if m else ""
