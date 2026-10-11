import time
from html import unescape
from urllib.parse import urljoin, urlparse, urldefrag, parse_qs, parse_qsl, urlencode, quote_plus

import requests
from bs4 import BeautifulSoup

from config import (
    SEED_URLS,
    USER_AGENT,
    REQUEST_TIMEOUT,
    MAX_LINKS_PER_PAGE,
    CRAWL_DELAY_SECONDS,
    SEARCH_DISCOVERY_ENABLED,
)

SCHOLARSHIP_TERMS = (
    "scholarship", "fellowship", "financial assistance", "financial aid",
    "student grant", "education grant", "stipend", "tuition support",
    "fee reimbursement", "student support scheme",
)
SKIP_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".zip", ".pdf", ".doc",
    ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".mp4", ".mp3",
)
TRACKING_PARAMS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


def normalize_url(url):
    """Normalize an HTTP(S) URL and remove fragments/tracking parameters."""
    if not url:
        return None
    try:
        url = unescape(url.strip())
        url, _fragment = urldefrag(url)
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        host = (parsed.hostname or "").lower()
        if scheme not in ("http", "https") or not host:
            return None
        if host.startswith("www."):
            host = host[4:]
        port = parsed.port
        netloc = host if not port or (scheme == "https" and port == 443) or (scheme == "http" and port == 80) else f"{host}:{port}"
        query_items = []
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            low = key.lower()
            if low.startswith("utm_") or low in TRACKING_PARAMS:
                continue
            query_items.append((key, value))
        query = urlencode(query_items, doseq=True)
        path = parsed.path or "/"
        if path != "/":
            path = path.rstrip("/")
        return parsed._replace(scheme=scheme, netloc=netloc, path=path, query=query, fragment="").geturl()
    except (ValueError, TypeError):
        return None


def _get(url):
    """Fetch HTML only; failures are handled by the caller and recorded by the crawler."""
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        timeout=REQUEST_TIMEOUT,
        allow_redirects=True,
    )
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "").lower()
    if content_type and "text/html" not in content_type and "application/xhtml" not in content_type:
        return None
    return response.text


def _has_relevant_text(text):
    lower = (text or "").lower()
    return any(term in lower for term in SCHOLARSHIP_TERMS)


def _search_result_url(href):
    """Unwrap common search-engine redirect links, otherwise return the href."""
    parsed = urlparse(href)
    if parsed.path == "/url":
        params = parse_qs(parsed.query)
        for key in ("q", "url"):
            if params.get(key):
                return unescape(params[key][0])
    return href


def search_discovery(max_results=30):
    """Search pages provide candidate URLs only; they are never used as source evidence."""
    if not SEARCH_DISCOVERY_ENABLED or max_results <= 0:
        return []

    candidates = []
    seen = set()
    queries = [
        "site:gov.in scholarship students India official",
        "site:ac.in scholarship students India",
        "India official university scholarship eligibility application",
        "India government fellowship students official",
        "India corporate foundation scholarship official",
    ]
    for query in queries:
        search_url = "https://www.google.com/search?q=" + quote_plus(query)
        try:
            html = _get(search_url)
            if not html:
                continue
            soup = BeautifulSoup(html, "html.parser")
            for anchor in soup.select("a[href]"):
                raw_href = anchor.get("href", "")
                href = _search_result_url(urljoin("https://www.google.com", raw_href))
                url = normalize_url(href)
                if not url or url in seen:
                    continue
                parsed = urlparse(url)
                host = (parsed.hostname or "").lower()
                if "google." in host or "googleusercontent." in host:
                    continue
                if parsed.path.lower().endswith(SKIP_EXTENSIONS):
                    continue
                label = anchor.get_text(" ", strip=True)
                # Avoid adding arbitrary navigation links from the search page.
                if not _has_relevant_text(label + " " + url):
                    continue
                seen.add(url)
                candidates.append({
                    "url": url,
                    "discovered_from": search_url,
                    "anchor_text": label,
                })
                if len(candidates) >= max_results:
                    return candidates
        except requests.RequestException:
            # Search engines commonly rate-limit automated requests; seed crawling still works.
            pass
        except Exception:
            pass
        time.sleep(CRAWL_DELAY_SECONDS)
    return candidates


def discover_candidates(seed_urls=None, max_pages=80):
    """Breadth-first link discovery with a bounded number of pages visited."""
    max_pages = max(1, int(max_pages or 1))
    seeds = seed_urls if seed_urls is not None else SEED_URLS
    queue = []
    seen = set()
    candidates = []
    candidate_urls = set()

    search_results = search_discovery(max_results=min(30, max_pages // 2))
    initial_urls = list(seeds) + [item["url"] for item in search_results]
    for raw_url in initial_urls:
        normalized = normalize_url(raw_url)
        if normalized and normalized not in seen:
            seen.add(normalized)
            queue.append(normalized)

    visited_pages = 0
    # Keep the discovery work bounded even when pages contain many irrelevant links.
    visit_limit = max(max_pages, max_pages * 2)
    while queue and visited_pages < visit_limit and len(candidates) < max_pages:
        url = queue.pop(0)
        try:
            html = _get(url)
            visited_pages += 1
            if not html:
                continue
            soup = BeautifulSoup(html, "html.parser")
            title = soup.title.get_text(" ", strip=True) if soup.title else ""
            body_text = soup.get_text(" ", strip=True)
            if _has_relevant_text(title + " " + body_text[:15000]) and url not in candidate_urls:
                candidates.append({
                    "url": url,
                    "discovered_from": "seed_or_discovered_link",
                    "anchor_text": title,
                })
                candidate_urls.add(url)

            base_host = (urlparse(url).hostname or "").lower().removeprefix("www.")
            links = []
            for anchor in soup.select("a[href]"):
                href = normalize_url(urljoin(url, anchor.get("href", "")))
                if not href or href in seen or urlparse(href).path.lower().endswith(SKIP_EXTENSIONS):
                    continue
                anchor_text = anchor.get_text(" ", strip=True)
                host = (urlparse(href).hostname or "").lower().removeprefix("www.")
                relevant = _has_relevant_text(anchor_text + " " + href)
                same_host = host == base_host
                # Prefer relevant links. Follow only a bounded number of same-host links too.
                if relevant or same_host:
                    priority = 0 if relevant else 1
                    links.append((priority, href))
            links.sort(key=lambda item: item[0])
            added = 0
            for _priority, href in links:
                if href in seen:
                    continue
                seen.add(href)
                queue.append(href)
                added += 1
                if added >= MAX_LINKS_PER_PAGE:
                    break
        except requests.RequestException:
            pass
        except Exception:
            # A malformed page should not stop discovery of other sources.
            pass
        finally:
            time.sleep(CRAWL_DELAY_SECONDS)

    return candidates[:max_pages]
