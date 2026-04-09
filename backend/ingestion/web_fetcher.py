"""Web page fetcher -- downloads HTML for ingestion into the knowledge graph.

Supports two modes:
    - Single-page fetch (fetch_page) for a known URL.
    - Shallow recursive crawl (fetch_with_crawl) that follows same-domain
      links up to a configurable depth, respecting a MAX_PAGES safety cap.

The returned FetchedPage objects carry raw HTML which is handed to
ingestion.parsers (as DocumentType.WEB) for Docling-based conversion.

Consumed by:
    - ingestion.pipeline  (calls fetch_with_crawl when processing web URLs)

Key design choices:
    - Only same-domain links are followed to avoid runaway crawls.
    - Non-HTML responses (images, CSS, JS) are silently skipped.
    - Title extraction uses a lightweight regex rather than a full HTML
      parser, keeping the dependency footprint small.
    - A custom User-Agent identifies the crawler for server logs.
"""

import logging
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30
MAX_PAGES = 20  # safety cap for crawl


@dataclass
class FetchedPage:
    url: str
    html: str
    title: str


async def fetch_page(url: str, timeout: int = DEFAULT_TIMEOUT) -> FetchedPage:
    """Fetch a single web page and return its HTML content.

    Args:
        url:     The URL to fetch.
        timeout: HTTP request timeout in seconds.

    Returns:
        FetchedPage with the URL, raw HTML, and extracted title.

    Raises:
        httpx.HTTPStatusError: If the server returns a non-2xx response.
    """
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=timeout,
        headers={"User-Agent": "Trident/0.1 (knowledge-ingestion)"},
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        html = resp.text

    # Extract title from HTML
    title = _extract_title(html) or urlparse(url).path or url

    return FetchedPage(url=url, html=html, title=title)


async def fetch_with_crawl(
    url: str,
    depth: int = 1,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[FetchedPage]:
    """Fetch a page and optionally crawl linked pages up to `depth` levels.

    depth=0: single page only
    depth=1: page + all same-domain links found on it
    depth=2: page + links + links from those pages
    """
    if depth < 0:
        depth = 0
    if depth > 3:
        depth = 3  # safety cap

    visited: set[str] = set()
    pages: list[FetchedPage] = []
    base_domain = urlparse(url).netloc

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=timeout,
        headers={"User-Agent": "Trident/0.1 (knowledge-ingestion)"},
    ) as client:
        await _crawl_recursive(
            client, url, base_domain, depth, visited, pages
        )

    logger.info(f"Fetched {len(pages)} pages from {url} (depth={depth})")
    return pages


async def _crawl_recursive(
    client: httpx.AsyncClient,
    url: str,
    base_domain: str,
    remaining_depth: int,
    visited: set[str],
    pages: list[FetchedPage],
) -> None:
    """Recursively fetch pages, staying on the same domain.

    Terminates when remaining_depth hits 0, the URL has already been
    visited, or the MAX_PAGES cap is reached.  HTTP errors on individual
    pages are logged and swallowed so the crawl continues.

    Args:
        client:          Shared httpx async client (connection pooling).
        url:             The URL to fetch in this recursion step.
        base_domain:     Domain restriction -- links outside this are ignored.
        remaining_depth: How many more link-follow hops are allowed.
        visited:         Mutable set of normalized URLs already fetched.
        pages:           Mutable list that accumulates FetchedPage results.
    """
    # Normalize URL
    normalized = _normalize_url(url)
    if normalized in visited or len(pages) >= MAX_PAGES:
        return
    visited.add(normalized)

    try:
        resp = await client.get(url)
        resp.raise_for_status()

        # Only process HTML responses
        content_type = resp.headers.get("content-type", "")
        if "text/html" not in content_type:
            logger.debug(f"Skipping non-HTML: {url} ({content_type})")
            return

        html = resp.text
        title = _extract_title(html) or urlparse(url).path
        pages.append(FetchedPage(url=url, html=html, title=title))
        logger.info(f"Fetched: {title} ({url})")

        # Crawl deeper if depth allows
        if remaining_depth > 0:
            links = _extract_links(html, url, base_domain)
            for link in links:
                if len(pages) >= MAX_PAGES:
                    break
                await _crawl_recursive(
                    client, link, base_domain,
                    remaining_depth - 1, visited, pages
                )

    except httpx.HTTPError as e:
        logger.warning(f"Failed to fetch {url}: {e}")
    except Exception as e:
        logger.warning(f"Error processing {url}: {e}")


def _normalize_url(url: str) -> str:
    """Normalize a URL by stripping fragments and trailing slashes.

    This ensures that "https://example.com/page#section" and
    "https://example.com/page/" are treated as the same page for
    deduplication purposes.
    """
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def _extract_title(html: str) -> str:
    """Quick title extraction without a full HTML parser."""
    import re
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()[:200]
    return ""


def _extract_links(html: str, base_url: str, base_domain: str) -> list[str]:
    """Extract same-domain HTTP(S) links from raw HTML.

    Filters out anchors, javascript/mailto URIs, and common non-content
    file extensions (images, fonts, archives) to keep the crawl focused
    on navigable pages.

    Args:
        html:        Raw HTML string to scan for href attributes.
        base_url:    The page URL, used to resolve relative hrefs.
        base_domain: Only links matching this domain are returned.

    Returns:
        Deduplicated list of absolute URLs on the same domain.
    """
    import re
    links: list[str] = []
    seen: set[str] = set()

    for match in re.finditer(r'href=["\']([^"\']+)["\']', html):
        href = match.group(1).strip()

        # Skip anchors, javascript, mailto
        if href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue

        # Resolve relative URLs
        full_url = urljoin(base_url, href)
        parsed = urlparse(full_url)

        # Same domain only
        if parsed.netloc != base_domain:
            continue

        # Skip non-HTTP
        if parsed.scheme not in ("http", "https"):
            continue

        # Skip common non-content extensions
        if any(parsed.path.endswith(ext) for ext in (
            ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
            ".css", ".js", ".woff", ".woff2", ".ttf",
            ".pdf", ".zip", ".tar", ".gz",
        )):
            continue

        normalized = _normalize_url(full_url)
        if normalized not in seen:
            seen.add(normalized)
            links.append(full_url)

    return links
