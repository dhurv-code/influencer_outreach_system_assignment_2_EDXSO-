from datetime import date, datetime, timezone
from urllib.parse import urlparse

from config import KNOWN_OFFICIAL_DOMAINS


def _host(url):
    try:
        return (urlparse(url or "").hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def _is_allowlisted(host):
    return any(host == domain or host.endswith("." + domain) for domain in KNOWN_OFFICIAL_DOMAINS)


def classify_source(url):
    """Classify the source and separately decide whether its domain is trusted."""
    host = _host(url)
    if not host:
        return "OTHER", False

    if host.endswith((".gov.in", ".nic.in")) or host in {"gov.in", "nic.in"}:
        return "GOVERNMENT", True
    if host.endswith((".ac.in", ".edu.in")):
        return "UNIVERSITY", True

    words = set(host.replace("-", ".").split("."))
    if any(word in words for word in ("foundation", "trust", "ngo", "charity")):
        source_type = "NGO_TRUST"
    elif any(word in words for word in ("international", "global", "iccr")):
        source_type = "INTERNATIONAL"
    elif any(word in words for word in ("corporate", "csr", "tata", "reliance", "infosys", "aditya", "mahindra", "wipro")):
        source_type = "CORPORATE_CSR"
    elif any(word in words for word in ("university", "college", "institute")):
        source_type = "UNIVERSITY"
    else:
        source_type = "OTHER"

    # A recognizable name is not proof. Non-government domains are trusted only if allowlisted.
    official = _is_allowlisted(host)
    if official and source_type == "OTHER":
        if any(token in host for token in ("aicte", "ugc", "education", "dst", "serb", "scholarships", "myscheme", "nsp")):
            source_type = "GOVERNMENT"
    return source_type, official


def calculate_confidence(record, source_is_official=None, now=None):
    """Deterministic score based on source trust and field-level evidence, not an LLM guess."""
    source_url = record.get("source_url") or record.get("official_source_url") or ""
    source_type, domain_official = classify_source(source_url)
    official = domain_official if source_is_official is None else bool(source_is_official)
    evidence = record.get("evidence") or {}
    score = 0
    reasons = []

    if official and record.get("official_source_url"):
        score += 25
        reasons.append("+25: source domain is recognized as an official source")
    else:
        reasons.append("+0: official primary source is not confirmed")

    name = (record.get("name") or "").strip()
    name_evidence = evidence.get("name")
    if name and len(name) >= 8 and name.casefold() not in {"scholarships", "scholarship", "home", "homepage"} and isinstance(name_evidence, dict) and name_evidence.get("snippet"):
        score += 20
        reasons.append("+20: specific scholarship name has source evidence")
    else:
        reasons.append("+0: specific scholarship name/evidence is missing")

    eligibility = record.get("eligibility")
    academic = record.get("academic_requirements")
    eligibility_evidence = evidence.get("eligibility") or evidence.get("academic_requirements")
    if (eligibility and eligibility != "Not specified" or academic and academic != "Not specified") and isinstance(eligibility_evidence, dict) and eligibility_evidence.get("snippet"):
        score += 15
        reasons.append("+15: eligibility or academic criteria have source evidence")
    else:
        reasons.append("+0: eligibility/academic evidence is missing")

    closing = record.get("closing_date")
    if closing and closing != "Not specified" and isinstance(evidence.get("closing_date"), dict) and evidence["closing_date"].get("snippet"):
        score += 15
        reasons.append("+15: closing date has field-level source evidence")
    else:
        reasons.append("+0: closing date is absent or not traceable")

    application_url = record.get("application_url")
    application_evidence = evidence.get("application_url")
    application_trusted = False
    if application_url and urlparse(application_url).scheme in ("http", "https") and isinstance(application_evidence, dict) and application_evidence.get("snippet"):
        score += 5
        reasons.append("+5: an application link is present in the source page")
        source_host = _host(source_url)
        application_host = _host(application_url)
        _app_type, app_domain_official = classify_source(application_url)
        if application_host == source_host or app_domain_official:
            score += 5
            application_trusted = True
            reasons.append("+5: application link points to the same or another recognized official domain")
        else:
            reasons.append("+0: application link points to a domain not independently recognized as official")
    else:
        reasons.append("+0: application link is absent or not traceable")

    evidence_fields = sum(
        1 for field, item in evidence.items()
        if field != "page_title" and isinstance(item, dict) and item.get("source_url") and item.get("snippet")
    )
    if evidence_fields >= 3:
        score += 10
        reasons.append(f"+10: {evidence_fields} fields have traceable snippets")
    elif evidence_fields >= 1:
        score += 5
        reasons.append(f"+5: only {evidence_fields} field(s) have traceable snippets")
    else:
        reasons.append("+0: no traceable field snippets")

    if record.get("content_hash") and source_url:
        score += 5
        reasons.append("+5: page content was fetched and fingerprinted in this run")
    else:
        reasons.append("+0: current page fetch/content hash is missing")

    score = min(100, score)
    # VERIFIED is deliberately strict: the score alone can never make an untrusted page official.
    verified = (
        score >= 95
        and official
        and bool(record.get("official_source_url"))
        and application_trusted
        and isinstance(name_evidence, dict)
        and bool(name_evidence.get("snippet"))
    )
    return {
        "confidence_score": round(float(score), 2),
        "verification_status": "VERIFIED" if verified else "REVIEW REQUIRED",
        "source_type": source_type,
        "confidence_reasons": reasons,
        "source_is_official": official,
    }


def _parse_date(value):
    if not value:
        return None
    value = str(value).strip()
    formats = (
        "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y",
        "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%B %d %Y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def determine_current_status(closing_date, source_present=True, misses=0, now=None):
    """Missing/ambiguous deadlines are not assumed active; repeated misses are explicit."""
    if not source_present:
        return "NO_LONGER_VERIFIABLE" if misses >= 3 else "REVIEW_REQUIRED"
    if not closing_date or str(closing_date).strip().casefold() in {"not specified", "none", "n/a", "unknown"}:
        return "REVIEW_REQUIRED"
    parsed = _parse_date(closing_date)
    if parsed is None:
        return "REVIEW_REQUIRED"
    today = now or datetime.now(timezone.utc).date()
    if isinstance(today, datetime):
        today = today.date()
    if isinstance(today, str):
        try:
            today = date.fromisoformat(today)
        except ValueError:
            today = datetime.now(timezone.utc).date()
    days_left = (parsed - today).days
    if days_left < 0:
        return "EXPIRED"
    if days_left <= 14:
        return "EXPIRING_SOON"
    return "ACTIVE"
