import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from urllib.parse import urlparse
import requests
from config import USER_AGENT, REQUEST_TIMEOUT, MAX_PAGES_PER_RUN, CRAWL_DELAY_SECONDS
from src.database import init_db, connect, utc_now, record_error
from src.discovery import discover_candidates, normalize_url
from src.extractor import extract_scholarship
from src.verifier import classify_source, calculate_confidence, determine_current_status
from src.change_detector import save_or_update, mark_url_miss

def fetch_html(url):
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "")
    if "text/html" not in content_type and "application/xhtml" not in content_type:
        raise ValueError(f"Unsupported content type: {content_type}")
    return response.text

def fingerprint_for(record):
    # Stable across crawls; changes to dates/amount do not create duplicate records.
    canonical = "|".join([
        (record.get("name") or "").strip().lower(),
        (record.get("provider") or "").strip().lower(),
        normalize_url(record.get("official_source_url") or "") or ""
    ])
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

def run_crawl(max_pages=None, db_path=None, seed_urls=None):
    init_db(db_path)
    started = utc_now()
    with connect(db_path) as conn:
        cursor = conn.execute("INSERT INTO crawl_runs(started_at,notes) VALUES(?,?)",
                              (started, "Crawler run started"))
        run_id = cursor.lastrowid

    discovered = discover_candidates(seed_urls=seed_urls, max_pages=max_pages or MAX_PAGES_PER_RUN)
    created = updated = crawled = errors = 0
    seen_fingerprints = set()

    for item in discovered:
        url = item["url"]
        try:
            html = fetch_html(url)
            crawled += 1
            record = extract_scholarship(html, url)
            if not record:
                mark_url_miss(url, db_path=db_path)
                time.sleep(CRAWL_DELAY_SECONDS)
                continue
            source_type, is_official = classify_source(url)
            record["source_type"] = source_type
            verification = calculate_confidence(record, source_is_official=is_official)
            record.update(verification)
            record["fingerprint"] = fingerprint_for(record)
            record["current_status"] = determine_current_status(record.get("closing_date"))
            record["confidence_reasons"] = json.dumps(record["confidence_reasons"], ensure_ascii=False)
            record["evidence_json"] = json.dumps(record.get("evidence", {}), ensure_ascii=False)
            result = save_or_update(record, db_path=db_path, run_id=run_id)
            seen_fingerprints.add(record["fingerprint"])
            if result["action"] == "created":
                created += 1
            elif result["action"] == "updated":
                updated += 1
        except Exception as exc:
            errors += 1
            record_error(url, exc, run_id=run_id, db_path=db_path)
            mark_url_miss(url, db_path=db_path)
        time.sleep(CRAWL_DELAY_SECONDS)

    # Existing records that were not successfully re-crawled are not immediately declared expired.
    # The system records misses only when their official URL was attempted and failed.
    with connect(db_path) as conn:
        conn.execute("""
            UPDATE crawl_runs SET finished_at=?, discovered_count=?, crawled_count=?,
            records_created=?, records_updated=?, errors_count=?, notes=? WHERE id=?
        """, (utc_now(), len(discovered), crawled, created, updated, errors,
              "Run completed. Search-result pages are discovery hints, never authoritative evidence.", run_id))

    return {
        "run_id": run_id, "discovered": len(discovered), "crawled": crawled,
        "created": created, "updated": updated, "errors": errors
    }

def main():
    parser = argparse.ArgumentParser(description="Scholarship Intelligence Crawler")
    parser.add_argument("--max-pages", type=int, default=MAX_PAGES_PER_RUN)
    parser.add_argument("--loop-hours", type=float, default=0,
                        help="Repeat indefinitely every N hours (0 means run once)")
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
