from src.verifier import classify_source, calculate_confidence, determine_current_status

def test_government_domain_is_official():
    source_type, official = classify_source("https://example.gov.in/scholarship")
    assert source_type == "GOVERNMENT"
    assert official is True

def test_aggregator_not_automatically_official():
    source_type, official = classify_source("https://example-blog.com/scholarships")
    assert official is False
    assert source_type == "OTHER"

def test_confidence_does_not_verify_unofficial_source():
    record = {
        "name": "A Specific Scholarship Programme",
        "official_source_url": "https://example-blog.com/scholarship",
        "eligibility": "Students enrolled in college",
        "academic_requirements": "Minimum marks",
        "closing_date": "31 August 2030",
        "application_url": "https://example-blog.com/apply",
        "evidence": {
            "name": {"source_url": "https://example-blog.com/scholarship", "snippet": "A Specific Scholarship Programme"},
            "closing_date": {"source_url": "https://example-blog.com/scholarship", "snippet": "Deadline 31 August 2030"},
            "academic_requirements": {"source_url": "https://example-blog.com/scholarship", "snippet": "Minimum marks required"}
        },
        "content_hash": "abc"
    }
    result = calculate_confidence(record)
    assert result["verification_status"] == "REVIEW REQUIRED"

def test_expired_status():
    assert determine_current_status("01 January 2020") == "EXPIRED"


def test_unknown_foundation_domain_is_classified_but_not_verified():
    source_type, official = classify_source("https://example-foundation.org/scholarship")
    assert source_type == "NGO_TRUST"
    assert official is False
