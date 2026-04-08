"""Fetch web pages for ingestion. Supports single page and shallow crawl."""

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
    """Fetch a single page and return its HTML."""
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
    """Recursively fetch pages, staying on the same domain."""
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
    """Strip fragments and trailing slashes for dedup."""
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
    """Extract same-domain links from HTML."""
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
