import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = Path(os.getenv("SCHOLARSHIP_DB_PATH", str(DATA_DIR / "scholarships.db")))
USER_AGENT = os.getenv(
    "CRAWLER_USER_AGENT",
    "ScholarshipIntelligenceCrawler/1.1 (educational project; respectful crawling)",
)
REQUEST_TIMEOUT = max(3, int(os.getenv("REQUEST_TIMEOUT", "15")))
MAX_PAGES_PER_RUN = max(1, int(os.getenv("MAX_PAGES_PER_RUN", "80")))
MAX_LINKS_PER_PAGE = max(1, int(os.getenv("MAX_LINKS_PER_PAGE", "30")))
CRAWL_DELAY_SECONDS = max(0.0, float(os.getenv("CRAWL_DELAY_SECONDS", "1.0")))
SEARCH_DISCOVERY_ENABLED = os.getenv("SEARCH_DISCOVERY_ENABLED", "true").strip().lower() in {
    "1", "true", "yes", "on"
}

# Seed sources are starting points, not a hard-coded list of scholarship records.
SEED_URLS = [
    "https://scholarships.gov.in/",
    "https://www.aicte-india.org/",
    "https://www.ugc.gov.in/",
    "https://www.education.gov.in/",
    "https://www.myscheme.gov.in/",
    "https://www.nsp.gov.in/",
    "https://www.inspireawards-dst.gov.in/",
]

# Exact provider domains that have been manually reviewed as official.
# Add a non-government provider only after checking that the domain belongs to it.
KNOWN_OFFICIAL_DOMAINS = {
    "scholarships.gov.in",
    "nsp.gov.in",
    "aicte-india.org",
    "ugc.gov.in",
    "education.gov.in",
    "myscheme.gov.in",
    "inspireawards-dst.gov.in",
    "dst.gov.in",
    "serbonline.in",
    "iccr.gov.in",
    "ugc.ac.in",
}
