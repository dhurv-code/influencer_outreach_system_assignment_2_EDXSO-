import hashlib
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

NOT_SPECIFIED = "Not specified"
SCHOLARSHIP_WORDS = re.compile(
    r"\b(scholarship|fellowship|student grant|financial assistance|education grant|stipend|fee reimbursement)\b",
    re.I,
)
DATE_PATTERN = (
    r"(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"
    r"\d{1,2}\s+[A-Za-z]+\s+\d{4}|[A-Za-z]+\s+\d{1,2},?\s+\d{4})"
)
GENERIC_TITLES = {
    "home", "homepage", "scholarships", "scholarship", "welcome", "home page",
    "student login", "login", "apply online", "national scholarship portal",
}


def _clean(value):
    return re.sub(r"\s+", " ", value or "").strip(" \t\r\n|–—-")


def _first_match(patterns, text, flags=re.I):
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return _clean(match.group(1))
    return NOT_SPECIFIED


def _evidence_for(value, text, field, source_url):
    if not value or value == NOT_SPECIFIED:
        return None
    idx = text.casefold().find(value.casefold())
    if idx < 0:
        # For page titles/heading values, the visible heading may differ slightly from body text.
        token = value.split()[0].casefold() if value.split() else ""
        idx = text.casefold().find(token) if token else -1
    if idx < 0:
        return None
    return {
        "source_url": source_url,
        "field": field,
        "value": value,
        "snippet": text[max(0, idx - 180): min(len(text), idx + len(value) + 180)],
    }


def _choose_name(soup):
    title = _clean(soup.title.get_text(" ", strip=True) if soup.title else "")
    meta = soup.find("meta", attrs={"property": "og:title"})
    og_title = _clean(meta.get("content", "")) if meta else ""
    headings = [_clean(node.get_text(" ", strip=True)) for node in soup.select("h1, h2")]
    candidates = [item for item in headings + [og_title, title] if item]
    # Prefer a specific title over a generic H1 such as "Scholarships".
    for candidate in candidates:
        normalized = re.sub(r"\s+", " ", candidate).lower()
        if normalized not in GENERIC_TITLES and len(candidate) >= 5:
            return candidate, title
    return (candidates[0] if candidates else ""), title


def _extract_provider(text):
    patterns = [
        r"(?:offered|provided|administered|sponsored|funded) by\s+([A-Z][A-Za-z0-9&'() -]{2,80})",
        r"(Ministry of [A-Z][A-Za-z &,-]{2,80})",
        r"(Government of India)",
        r"(Government of [A-Z][A-Za-z &-]{2,40})",
        r"(University of [A-Z][A-Za-z &,-]{2,80})",
    ]
    provider = _first_match(patterns, text)
    if provider != NOT_SPECIFIED:
        return provider
    return NOT_SPECIFIED


def _extract_application_link(soup, source_url, text):
    apply_terms = ("apply now", "apply online", "application form", "register now", "apply here", "online application")
    for anchor in soup.select("a[href]"):
        label = _clean(anchor.get_text(" ", strip=True))
        href = urljoin(source_url, anchor.get("href", ""))
        parsed = urlparse(href)
        if any(term in label.casefold() for term in apply_terms) and parsed.scheme in ("http", "https"):
            snippet = f"Link text: {label}; URL: {href}"
            return href, {"source_url": source_url, "field": "application_url", "value": href, "snippet": snippet}
    return None, None


def extract_scholarship(html, source_url):
    """Extract a candidate record without inventing fields absent from the page."""
    soup = BeautifulSoup(html or "", "html.parser")
    for node in soup(["script", "style", "noscript", "svg", "nav", "footer", "header"]):
        node.decompose()

    name, page_title = _choose_name(soup)
    text = _clean(soup.get_text(" ", strip=True))
    if len(text) < 100 or not SCHOLARSHIP_WORDS.search(name + " " + text[:15000]):
        return None

    amount = _first_match([
        r"((?:INR|Rs\.?|₹)\s*[\d,]+(?:\.\d+)?(?:\s*(?:per month|per annum|annually|one time|per year))?)",
        r"((?:INR|Rs\.?|₹)\s*[\d,.]+\s*(?:lakh|lakhs|crore|crores)(?:\s*(?:per month|per annum|annually|per year))?)",
        r"([\d,.]+\s*(?:rupees|lakh|lakhs|crore|crores)(?:\s*(?:per month|per annum|annually|per year))?)",
    ], text)
    closing = _first_match([
        rf"(?:last date|application deadline|closing date|applications close|deadline)\s*(?:is|:|-|on|for)?\s*({DATE_PATTERN})",
    ], text)
    opening = _first_match([
        rf"(?:application opens|opening date|applications start|start date)\s*(?:is|:|-|on)?\s*({DATE_PATTERN})",
    ], text)
    income = _first_match([
        r"((?:family|annual|parental|household) income[^.;]{0,160}(?:₹|Rs\.?|INR)?\s*[\d,.]+[^.;]{0,40})",
        r"((?:income limit|income should not exceed|annual income should be)[^.;]{0,180})",
    ], text)
    age = _first_match([r"((?:age limit|aged between|age should be|age criteria)[^.;]{0,140})"], text)
    gender = _first_match([r"((?:female students|girls only|women candidates|male candidates|gender criteria)[^.;]{0,120})"], text)
    category = _first_match([r"((?:SC/ST/OBC|SC candidates|ST candidates|OBC candidates|minority students|category criteria)[^.;]{0,160})"], text)
    domicile = _first_match([r"((?:domicile|resident of|residents of|state of)[^.;]{0,160})"], text)
    academic = _first_match([r"((?:minimum marks|academic performance|marks obtained|percentage|CGPA|merit)[^.;]{0,160})"], text)
    level = _first_match([r"((?:Class\s+[IVX0-9]+|undergraduate|postgraduate|Ph\.?D\.?|doctoral|school students|college students)[^.;]{0,120})"], text)
    documents = _first_match([r"((?:documents required|documents needed|required documents)[^.;]{0,260})"], text)
    selection = _first_match([r"((?:selection process|selection will be|shortlisted|selection criteria)[^.;]{0,200})"], text)
    renewal = _first_match([r"((?:renewal|renewed|continuation criteria)[^.;]{0,200})"], text)
    eligibility = _first_match([
        r"((?:eligibility criteria|eligibility|eligible candidates|who can apply)\s*[:\-]?\s*[^.;]{1,500})",
    ], text)
    provider = _extract_provider(text)
    application_url, application_evidence = _extract_application_link(soup, source_url, text)

    # Reject directory/home pages that mention scholarships but do not describe one opportunity.
    generic_name = name.casefold().strip() in GENERIC_TITLES
    meaningful_fields = [amount, closing, opening, income, age, category, domicile, academic, documents, selection, eligibility]
    if generic_name or sum(value != NOT_SPECIFIED for value in meaningful_fields) < 1:
        return None

    evidence = {}
    field_values = {
        "name": name,
        "provider": provider,
        "amount_benefit": amount,
        "eligibility": eligibility,
        "closing_date": closing,
        "opening_date": opening,
        "income_criteria": income,
        "age_criteria": age,
        "gender_criteria": gender,
        "category_criteria": category,
        "domicile_criteria": domicile,
        "academic_requirements": academic,
        "education_level": level,
        "documents_required": documents,
        "selection_process": selection,
        "renewal_requirements": renewal,
    }
    for field, value in field_values.items():
        item = _evidence_for(value, text, field, source_url)
        if item:
            evidence[field] = item
    if application_evidence:
        evidence["application_url"] = application_evidence
    evidence["page_title"] = {
        "source_url": source_url,
        "value": page_title or name,
        "snippet": f"Page title: {page_title or name}. Page excerpt: {text[:350]}",
    }
    content_hash = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()

    return {
        "name": name or NOT_SPECIFIED,
        "provider": provider,
        "source_url": source_url,
        # crawler.py sets official_source_url only after source classification.
        "official_source_url": "",
        "application_url": application_url,
        "amount_benefit": amount,
        "eligibility": eligibility,
        "academic_requirements": academic,
        "education_level": level,
        "income_criteria": income,
        "age_criteria": age,
        "gender_criteria": gender,
        "category_criteria": category,
        "domicile_criteria": domicile,
        "institution_criteria": NOT_SPECIFIED,
        "opening_date": opening,
        "closing_date": closing,
        "documents_required": documents,
        "selection_process": selection,
        "renewal_requirements": renewal,
        "evidence": evidence,
        "content_hash": content_hash,
        "page_text_length": len(text),
    }
