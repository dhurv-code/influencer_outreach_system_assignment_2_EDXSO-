import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = Path(os.getenv("SCHOLARSHIP_DB_PATH", DATA_DIR / "scholarships.db"))
USER_AGENT = os.getenv(
    "CRAWLER_USER_AGENT",
    "ScholarshipIntelligenceCrawler/1.0 (educational project; respectful crawling)"
)
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "15"))
MAX_PAGES_PER_RUN = int(os.getenv("MAX_PAGES_PER_RUN", "80"))
MAX_LINKS_PER_PAGE = int(os.getenv("MAX_LINKS_PER_PAGE", "30"))
CRAWL_DELAY_SECONDS = float(os.getenv("CRAWL_DELAY_SECONDS", "1.0"))
SEARCH_DISCOVERY_ENABLED = os.getenv("SEARCH_DISCOVERY_ENABLED", "true").lower() == "true"

# Starting points only. The crawler also discovers candidate pages from links and search results.
SEED_URLS = [
    "https://scholarships.gov.in/",
    "https://www.aicte-india.org/",
    "https://www.ugc.gov.in/",
    "https://www.education.gov.in/",
    "https://www.myscheme.gov.in/",
    "https://www.nsp.gov.in/",
    "https://www.inspireawards-dst.gov.in/",
]

# Official domains that can be recognized when a provider uses a non-government domain.
# Add domains only after manually checking that they belong to the actual provider.
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


# import os

# from dotenv import load_dotenv

# load_dotenv()

# GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# DB_PATH = os.path.join(os.path.dirname(__file__), "data", "scholarships.db")

# # Seed URLs for intelligent discovery (Government, Universities, CSRs)
# SEED_DISCOVERY_URLS = [
#     "https://scholarships.gov.in/",
#     "https://www.education.gov.in/scholarships",
#     "https://www.buddy4study.com/scholarships", # Used as aggregator for discovery ONLY
# ]

# OFFICIAL_DOMAIN_SUFFIXES = [".gov.in", ".edu.in", ".ac.in", ".org", ".nic.in"]