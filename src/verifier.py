from datetime import datetime, timezone
from urllib.parse import urlparse
from config import KNOWN_OFFICIAL_DOMAINS

def classify_source(url):
    host = urlparse(url or "").netloc.lower().split(":")[0].removeprefix("www.")
    if not host:
        return "OTHER", False
    if host.endswith(".gov.in") or host.endswith(".nic.in") or host in {"gov.in", "nic.in"}:
        return "GOVERNMENT", True
    if host.endswith(".ac.in") or host.endswith(".edu.in"):
        return "UNIVERSITY", True
    if host in KNOWN_OFFICIAL_DOMAINS:
        if "aicte" in host or "ugc" in host or "education.gov.in" in host:
            return "GOVERNMENT", True
        return "GOVERNMENT", True
    # Classification is not proof of authenticity. These heuristics label source type only;
    # unknown domains still fail the official-source gate until reviewed and allowlisted.
    host_words = host.replace("-", ".").split(".")
    if any(word in host_words for word in ("foundation", "trust", "ngo", "charity")):
        return "NGO_TRUST", False
    if any(word in host_words for word in ("international", "global", "iccr")):
        return "INTERNATIONAL", False
    if any(word in host_words for word in ("corporate", "csr", "tata", "reliance", "infosys", "aditya")):
        return "CORPORATE_CSR", False
    return "OTHER", False

def calculate_confidence(record, source_is_official=None, now=None):
    """Deterministic evidence-based score; not an LLM-generated probability."""
    source_type, domain_official = classify_source(record.get("official_source_url", ""))
    official = domain_official if source_is_official is None else bool(source_is_official)
    evidence = record.get("evidence") or {}
    score = 0
    reasons = []

    if official:
        score += 25
        reasons.append("+25: source domain matches an official government, university, or allowlisted provider domain")
    else:
        reasons.append("+0: source domain is not confirmed as official")

    name = (record.get("name") or "").strip()
    if name and name.lower() not in {"scholarships", "scholarship", "home", "homepage"} and len(name) >= 8:
        score += 20
        reasons.append("+20: page has a specific scholarship title")
    else:
        reasons.append("+0: no specific scholarship title could be established")

    eligibility = record.get("eligibility", "Not specified")
    academic = record.get("academic_requirements", "Not specified")
    if eligibility != "Not specified" or academic != "Not specified":
        if any(k in evidence for k in ("name", "academic_requirements")) or eligibility != "Not specified":
            score += 15
            reasons.append("+15: eligibility or academic criteria were extracted from page text")
    else:
        reasons.append("+0: eligibility evidence is missing")

    deadline = record.get("closing_date", "Not specified")
    if deadline != "Not specified" and evidence.get("closing_date"):
        score += 15
        reasons.append("+15: closing date has field-level source evidence")
    else:
        reasons.append("+0: closing date is absent or not traceable")

    app_url = record.get("application_url")
    if app_url and urlparse(app_url).scheme in ("http", "https"):
        score += 10
        reasons.append("+10: an application link was found on the page")
    else:
        reasons.append("+0: no application link was found")

    evidence_fields = sum(
        1 for k, v in evidence.items()
        if isinstance(v, dict) and v.get("source_url") and v.get("snippet")
    )
    if evidence_fields >= 3:
        score += 10
        reasons.append(f"+10: {evidence_fields} extracted fields have traceable snippets")
    elif evidence_fields >= 1:
        score += 5
        reasons.append(f"+5: only {evidence_fields} field(s) have traceable snippets")
    else:
        reasons.append("+0: no traceable field snippets")

    verified_at = now or datetime.now(timezone.utc)
    if verified_at.tzinfo is None:
        verified_at = verified_at.replace(tzinfo=timezone.utc)
    # This check represents a successful current fetch. Historical stored timestamps are not used.
    if record.get("content_hash") and record.get("official_source_url"):
        score += 5
        reasons.append("+5: source page was successfully fetched during this verification run")
    else:
        reasons.append("+0: no current source fetch/content hash")

    score = min(100, score)
    # Mandatory gate: a score alone cannot override the source-authenticity requirement.
    verified = score >= 95 and official and bool(evidence.get("name"))
    return {
        "confidence_score": round(float(score), 2),
        "verification_status": "VERIFIED" if verified else "REVIEW REQUIRED",
        "source_type": source_type,
        "confidence_reasons": reasons,
        "source_is_official": official
    }

def determine_current_status(closing_date, source_present=True, misses=0, now=None):
    if not source_present:
        return "NO_LONGER_VERIFIABLE" if misses >= 3 else "REVIEW_REQUIRED"
    if not closing_date or closing_date == "Not specified":
        return "ACTIVE"
    now = now or datetime.now(timezone.utc).date()
    elif_date = _parse_date(closing_date)
    if not elif_date:
        return "ACTIVE"
    delta = (elif_date - now).days
    if delta < 0:
        return "EXPIRED"
    if delta <= 14:
        return "EXPIRING_SOON"
    return "ACTIVE"

def _parse_date(value):
    from datetime import datetime
    formats = ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y",
               "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%B %d %Y")
    for fmt in formats:
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


