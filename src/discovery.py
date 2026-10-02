import time
from urllib.parse import urljoin, urlparse, urldefrag, quote_plus
import requests
from bs4 import BeautifulSoup
from config import (
    SEED_URLS, USER_AGENT, REQUEST_TIMEOUT, MAX_LINKS_PER_PAGE,
    CRAWL_DELAY_SECONDS, SEARCH_DISCOVERY_ENABLED
)

SCHOLARSHIP_TERMS = (
    "scholarship", "fellowship", "financial assistance", "financial aid",
    "student grant", "education grant", "stipend", "tuition support", "fee reimbursement"
)
SKIP_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".svg", ".zip", ".pdf", ".doc", ".docx", ".xls", ".xlsx")

def normalize_url(url):
    if not url:
        return None
    url, _ = urldefrag(url.strip())
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    return url.rstrip("/")

def _get(url):
    headers = {"User-Agent": USER_AGENT}
    response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "")
    if "text/html" not in content_type and "application/xhtml" not in content_type:
        return None
    return response.text

def _has_relevant_text(text):
    lower = text.lower()
    return any(term in lower for term in SCHOLARSHIP_TERMS)

def search_discovery(max_results=30):
    """Use public search result pages for candidate discovery only; never treat search snippets as evidence."""
    if not SEARCH_DISCOVERY_ENABLED:
        return []
    candidates = []
    queries = [
        "site:gov.in scholarship students India official",
        "site:ac.in scholarship students India",
        "India official university scholarship eligibility application",
        "India government fellowship students official",
        "India corporate foundation scholarship official"
    ]
    for query in queries:
        search_url = "https://www.google.com/search?q=" + quote_plus(query)
        try:
            html = _get(search_url)
            if not html:
                continue
            soup = BeautifulSoup(html, "html.parser")
            for a in soup.select("a[href]"):
                href = a.get("href", "")
                if href.startswith("/url?q="):
                    href = href.split("/url?q=", 1)[1].split("&", 1)[0]
                url = normalize_url(href)
                if not url:
                    continue
                host = urlparse(url).netloc.lower()
                if "google." in host or "googleusercontent." in host:
                    continue
                text = a.get_text(" ", strip=True)
                if urlparse(url).path.lower().endswith(SKIP_EXTENSIONS):
                    continue
                candidates.append({"url": url, "discovered_from": search_url, "anchor_text": text})
                if len(candidates) >= max_results:
                    return candidates
        except Exception:
            pass
        time.sleep(CRAWL_DELAY_SECONDS)
    return candidates

def discover_candidates(seed_urls=None, max_pages=80):
    """Breadth-first discovery from seed sources plus search candidates."""
    seeds = seed_urls or SEED_URLS
    queue = []
    seen = set()
    candidates = []
    for url in list(seeds) + [x["url"] for x in search_discovery(max_results=max_pages // 2)]:
        normalized = normalize_url(url)
        if normalized and normalized not in seen:
            seen.add(normalized)
            queue.append(normalized)

    while queue and len(candidates) < max_pages:
        url = queue.pop(0)
        try:
            html = _get(url)
            if not html:
                continue
            soup = BeautifulSoup(html, "html.parser")
            title = soup.title.get_text(" ", strip=True) if soup.title else ""
            body_text = soup.get_text(" ", strip=True)
            if _has_relevant_text(title + " " + body_text[:12000]):
                candidates.append({
                    "url": url,
                    "discovered_from": "seed_or_discovered_link",
                    "anchor_text": title
                })
            links_added = 0
            base_host = urlparse(url).netloc.lower().removeprefix("www.")
            for a in soup.select("a[href]"):
                href = normalize_url(urljoin(url, a.get("href", "")))
                if not href or href in seen or urlparse(href).path.lower().endswith(SKIP_EXTENSIONS):
                    continue
                anchor = a.get_text(" ", strip=True)
                host = urlparse(href).netloc.lower().removeprefix("www.")
                # Follow relevant same-site links first, while allowing official links to other domains.
                relevant = _has_relevant_text(anchor + " " + href)
                same_host = host == base_host
                if relevant or same_host:
                    seen.add(href)
                    queue.append(href)
                    links_added += 1
                if links_added >= MAX_LINKS_PER_PAGE:
                    break
            time.sleep(CRAWL_DELAY_SECONDS)
        except Exception:
            continue
    # Keep the first occurrence of each normalized URL.
    unique = {}
    for item in candidates:
        unique.setdefault(item["url"], item)
    return list(unique.values())[:max_pages]


