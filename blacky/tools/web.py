"""
Web search, scraping, and browser automation tools for BlackyAgent.
"""

import subprocess
import requests
from bs4 import BeautifulSoup
from blacky.tools.base import registry


@registry.register
def search_web(query: str, max_results: int = 5) -> str:
    """
    Search the live web using DuckDuckGo.
    Returns titles, snippets, and source URLs.
    """
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS

            ddgs = DDGS()
            results = list(ddgs.text(query, max_results=max_results))

        if not results:
            res = f"No web search results found for: '{query}'"
            registry.log_call("search_web", {"query": query}, res, success=True)
            return res

        formatted = []
        for i, item in enumerate(results, 1):
            title = item.get("title", "No Title")
            body = item.get("body", "")
            href = item.get("href", "")
            formatted.append(f"{i}. {title}\n   URL: {href}\n   Snippet: {body}\n")

        res_str = f"Web Search Results for '{query}':\n\n" + "\n".join(formatted)
        registry.log_call("search_web", {"query": query}, f"Found {len(results)} results", success=True)
        return res_str
    except Exception as e:
        err = f"Web search failed: {str(e)}"
        registry.log_call("search_web", {"query": query}, err, success=False)
        return err


@registry.register
def fetch_webpage(url: str, max_chars: int = 4000) -> str:
    """
    Fetch and extract clean readable text/articles from a webpage URL.
    """
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }
        resp = requests.get(url, headers=headers, timeout=12)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Strip scripts, stylesheets, and meta elements
        for element in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            element.extract()

        text = soup.get_text(separator=" ", strip=True)
        text = " ".join(text.split())

        if len(text) > max_chars:
            text = text[:max_chars] + f"\n... [Truncated {len(text) - max_chars} characters]"

        res = f"Content extracted from {url}:\n\n{text}"
        registry.log_call("fetch_webpage", {"url": url}, f"Extracted {len(text)} chars", success=True)
        return res
    except Exception as e:
        err = f"Failed to fetch webpage '{url}': {str(e)}"
        registry.log_call("fetch_webpage", {"url": url}, err, success=False)
        return err


@registry.register
def open_in_browser(url: str) -> str:
    """
    Open any website or URL directly in the macOS default web browser (Safari/Chrome).
    """
    try:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        subprocess.run(["open", url], check=True)
        res = f"Opened {url} in default web browser."
        registry.log_call("open_in_browser", {"url": url}, res, success=True)
        return res
    except Exception as e:
        err = f"Failed to open browser: {str(e)}"
        registry.log_call("open_in_browser", {"url": url}, err, success=False)
        return err
