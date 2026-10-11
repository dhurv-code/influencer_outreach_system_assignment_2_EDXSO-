import argparse
import hashlib
import json
import time
from urllib.parse import urlparse

import requests

from config import USER_AGENT, REQUEST_TIMEOUT, MAX_PAGES_PER_RUN, CRAWL_DELAY_SECONDS
from src.database import init_db, connect, utc_now, record_error
from src.discovery import discover_candidates, normalize_url
from src.extractor import extract_scholarship
from src.verifier import classify_source, calculate_confidence, determine_current_status
from src.change_detector import save_or_update, mark_url_miss


def fetch_html(url, return_final_url=False):
    """Fetch a webpage and reject non-HTML responses instead of parsing files as pages."""
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
        timeout=REQUEST_TIMEOUT,
        allow_redirects=True,
    )
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "").lower()
    if content_type and "text/html" not in content_type and "application/xhtml" not in content_type:
        raise ValueError(f"Unsupported content type: {content_type}")
    final_url = normalize_url(response.url) or url
    return (response.text, final_url) if return_final_url else response.text


def fingerprint_for(record):
    """Stable identity based on the scholarship and the page it came from, not mutable fields."""
    source_url = normalize_url(record.get("source_url") or record.get("official_source_url") or "") or ""
    canonical = "|".join([
        (record.get("name") or "").strip().casefold(),
        (record.get("provider") or "").strip().casefold(),
        source_url,
    ])
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _existing_source_candidates(db_path=None):
    """Revisit known source URLs on every run so existing records can be updated or marked stale."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT source_url, official_source_url FROM scholarships WHERE source_url<>'' OR official_source_url<>''"
        ).fetchall()
    items = []
    for row in rows:
        url = normalize_url(row["source_url"] or row["official_source_url"])
        if url:
            items.append({"url": url, "discovered_from": "previous_database_record", "anchor_text": "Previously stored source"})
    return items


def run_crawl(max_pages=None, db_path=None, seed_urls=None):
    init_db(db_path)
    started = utc_now()
    with connect(db_path) as conn:
        cursor = conn.execute(
            "INSERT INTO crawl_runs(started_at,notes) VALUES(?,?)",
            (started, "Crawler run started"),
        )
        run_id = cursor.lastrowid

    errors = 0
    try:
        discovered = discover_candidates(seed_urls=seed_urls, max_pages=max_pages or MAX_PAGES_PER_RUN)
    except Exception as exc:
        discovered = []
        errors += 1
        record_error("DISCOVERY", exc, run_id=run_id, db_path=db_path)

    # Re-crawl existing records even if discovery no longer finds their pages.
    combined = []
    seen_urls = set()
    for item in list(discovered) + _existing_source_candidates(db_path):
        url = normalize_url(item.get("url"))
        if url and url not in seen_urls:
            seen_urls.add(url)
            combined.append({**item, "url": url})

    created = updated = crawled = 0
    for item in combined:
        url = item["url"]
        try:
            html, final_url = fetch_html(url, return_final_url=True)
            crawled += 1
            record = extract_scholarship(html, final_url)
            if not record:
                mark_url_miss(final_url, db_path=db_path)
                if final_url != url:
                    mark_url_miss(url, db_path=db_path)
                continue

            source_type, is_official = classify_source(final_url)
            record["source_url"] = final_url
            record["source_is_official"] = bool(is_official)
            # Never label an unconfirmed or aggregator URL as the official source.
            record["official_source_url"] = final_url if is_official else ""
            record["source_type"] = source_type
            checked_at = utc_now()
            for item_evidence in record.get("evidence", {}).values():
                if isinstance(item_evidence, dict):
                    item_evidence.setdefault("observed_at", checked_at)

            verification = calculate_confidence(record, source_is_official=is_official)
            record.update(verification)
            record["fingerprint"] = fingerprint_for(record)
            record["current_status"] = determine_current_status(record.get("closing_date"))
            record["confidence_reasons"] = json.dumps(record["confidence_reasons"], ensure_ascii=False)
            record["evidence_json"] = json.dumps(record.get("evidence", {}), ensure_ascii=False)
            result = save_or_update(record, db_path=db_path, run_id=run_id)
            if result["action"] == "created":
                created += 1
            elif result["action"] == "updated":
                updated += 1
        except Exception as exc:
            errors += 1
            record_error(url, exc, run_id=run_id, db_path=db_path)
            mark_url_miss(url, db_path=db_path)
        finally:
            time.sleep(CRAWL_DELAY_SECONDS)

    with connect(db_path) as conn:
        conn.execute(
            """UPDATE crawl_runs
               SET finished_at=?, discovered_count=?, crawled_count=?, records_created=?,
                   records_updated=?, errors_count=?, notes=? WHERE id=?""",
            (
                utc_now(), len(combined), crawled, created, updated, errors,
                "Run completed. Search results are discovery hints only; VERIFIED requires an official source and traceable evidence.",
                run_id,
            ),
        )

    return {
        "run_id": run_id,
        "discovered": len(combined),
        "crawled": crawled,
        "created": created,
        "updated": updated,
        "errors": errors,
    }


def main():
    parser = argparse.ArgumentParser(description="Scholarship Intelligence Crawler")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES_PER_RUN)
    parser.add_argument(
        "--loop-hours", type=float, default=0,
        help="Repeat indefinitely every N hours (0 means run once)",
    )
    args = parser.parse_args()
    init_db()
    while True:
        result = run_crawl(max_pages=args.max_pages)
        print(json.dumps(result, indent=2))
        if args.loop_hours <= 0:
            break
        time.sleep(max(1, args.loop_hours * 3600))


if __name__ == "__main__":
    main()
