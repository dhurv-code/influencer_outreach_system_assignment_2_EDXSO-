import hashlib
import re
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

NOT_SPECIFIED = "Not specified"
SCHOLARSHIP_WORDS = re.compile(r"\b(scholarship|fellowship|student grant|financial assistance|education grant|stipend|fee reimbursement)\b", re.I)

def _clean(value):
    return re.sub(r"\s+", " ", value or "").strip()

def _first_match(patterns, text, flags=re.I):
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return _clean(match.group(1))
    return NOT_SPECIFIED

def _evidence_for(value, text, field):
    if not value or value == NOT_SPECIFIED:
        return None
    idx = text.lower().find(value.lower())
    if idx < 0:
        # Evidence can use a nearby sentence containing the extracted date/amount.
        token = value.split()[0].lower()
        idx = text.lower().find(token)
    if idx < 0:
        return None
    return {"field": field, "value": value, "snippet": text[max(0, idx-180):min(len(text), idx+len(value)+180)]}

def extract_scholarship(html, source_url):
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
        node.decompose()
    title = _clean(soup.title.get_text(" ", strip=True) if soup.title else "")
    headings = [_clean(h.get_text(" ", strip=True)) for h in soup.select("h1,h2")]
    page_heading = next((h for h in headings if h), "")
    name = page_heading or title
    text = _clean(soup.get_text(" ", strip=True))
    if len(text) < 100 or not SCHOLARSHIP_WORDS.search(name + " " + text[:10000]):
        return None

    # Avoid storing broad directory/home pages as scholarship records unless the page itself
    # appears to describe a particular funding opportunity.
    generic_titles = {"home", "homepage", "scholarships", "scholarship", "welcome"}
    if name.lower().strip() in generic_titles and not re.search(r"(apply|eligibility|amount|last date|deadline)", text, re.I):
        return None

    amount = _first_match([
        r"((?:INR|Rs\.?|₹)\s?[\d,]+(?:\s?(?:per month|per annum|annually|one time|per year))?)",
        r"([\d,]+\s?(?:rupees|lakh|lakhs|crore|crores)(?:\s?(?:per month|per annum|annually|per year))?)"
    ], text)
    closing = _first_match([
        r"(?:last date|application deadline|closing date|applications close|deadline)\s*(?:is|:|-|on)?\s*((?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4})|(?:\d{1,2}\s+[A-Za-z]+\s+\d{4})|(?:[A-Za-z]+\s+\d{1,2},?\s+\d{4}))",
    ], text)
    opening = _first_match([
        r"(?:application opens|opening date|applications start|start date)\s*(?:is|:|-|on)?\s*((?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4})|(?:\d{1,2}\s+[A-Za-z]+\s+\d{4})|(?:[A-Za-z]+\s+\d{1,2},?\s+\d{4}))"
    ], text)
    income = _first_match([
        r"((?:family|annual|parental|household) income[^.]{0,120}(?:₹|Rs\.?|INR)?\s?[\d,]+[^.]{0,40})",
        r"((?:income limit|income should not exceed|annual income should be)[^.]{0,160})"
    ], text)
    age = _first_match([r"((?:age limit|aged between|age should be|age criteria)[^.]{0,120})"], text)
    gender = _first_match([r"((?:female students|girls only|women candidates|male candidates|gender criteria)[^.]{0,100})"], text)
    category = _first_match([r"((?:SC/ST/OBC|SC candidates|ST candidates|OBC candidates|minority students|category criteria)[^.]{0,140})"], text)
    domicile = _first_match([r"((?:domicile|resident of|residents of|state of)[^.]{0,140})"], text)
    academic = _first_match([r"((?:minimum marks|academic performance|marks obtained|percentage|CGPA|merit)[^.]{0,140})"], text)
    level = _first_match([r"((?:Class [IVX0-9]+|class [0-9]+|undergraduate|postgraduate|Ph\.?D\.?|doctoral|school students|college students)[^.]{0,100})"], text)
    documents = _first_match([r"((?:documents required|documents needed|required documents)[^.]{0,250})"], text)
    selection = _first_match([r"((?:selection process|selection will be|shortlisted|selection criteria)[^.]{0,180})"], text)
    renewal = _first_match([r"((?:renewal|renewed|continuation criteria)[^.]{0,180})"], text)

    app_url = None
    for a in soup.select("a[href]"):
        label = _clean(a.get_text(" ", strip=True)).lower()
        href = urljoin(source_url, a.get("href", ""))
        if any(term in label for term in ("apply now", "apply online", "application form", "register now", "apply here")):
            if urlparse(href).scheme in ("http", "https"):
                app_url = href
                break

    host = urlparse(source_url).netloc.lower().removeprefix("www.")
    provider = _clean(re.sub(r"^(the\s+)?", "", host.split(".")[0]).replace("-", " ").title())
    if any(term in text.lower() for term in ("ministry of", "government of india", "government of")):
        provider_match = re.search(r"(Ministry of [A-Z][A-Za-z &,-]{3,80}|Government of India|Government of [A-Z][A-Za-z ]{2,40})", text)
        if provider_match:
            provider = _clean(provider_match.group(1))

    evidence = {}
    for field, value in {
        "name": name, "provider": provider, "amount_benefit": amount,
        "closing_date": closing, "opening_date": opening, "income_criteria": income,
        "age_criteria": age, "gender_criteria": gender, "category_criteria": category,
        "domicile_criteria": domicile, "academic_requirements": academic,
        "education_level": level, "documents_required": documents,
        "selection_process": selection, "renewal_requirements": renewal
    }.items():
        ev = _evidence_for(value, text, field)
        if ev:
            evidence[field] = {"source_url": source_url, **ev}
    evidence["page_title"] = {"source_url": source_url, "value": title, "snippet": text[:400]}
    content_hash = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()

    return {
        "name": name or "Untitled scholarship",
        "provider": provider or "Not specified",
        "official_source_url": source_url,
        "application_url": app_url,
        "amount_benefit": amount,
        "eligibility": _first_match([
            r"((?:eligibility|eligible candidates|who can apply)[^.]{0,500})"
        ], text),
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
        "page_text_length": len(text)
    }


