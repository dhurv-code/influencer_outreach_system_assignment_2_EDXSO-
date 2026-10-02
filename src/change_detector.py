from datetime import datetime, timezone
from src.database import connect, utc_now

TRACKED_FIELDS = [
    "name", "provider", "application_url", "amount_benefit", "eligibility",
    "academic_requirements", "education_level", "income_criteria", "age_criteria",
    "gender_criteria", "category_criteria", "domicile_criteria", "institution_criteria",
    "opening_date", "closing_date", "documents_required", "selection_process",
    "renewal_requirements", "current_status", "verification_status", "confidence_score"
]

def save_or_update(record, db_path=None, run_id=None):
    """Insert a new record or update it while preserving changed field values in change_log."""
    fingerprint = record["fingerprint"]
    now = utc_now()
    evidence_json = record.get("evidence_json", "{}")
    with connect(db_path) as conn:
        old = conn.execute("SELECT * FROM scholarships WHERE fingerprint=?", (fingerprint,)).fetchone()
        if old is None:
            fields = [
                "fingerprint","name","provider","official_source_url","application_url","source_type",
                "amount_benefit","eligibility","academic_requirements","education_level","income_criteria",
                "age_criteria","gender_criteria","category_criteria","domicile_criteria","institution_criteria",
                "opening_date","closing_date","documents_required","selection_process","renewal_requirements",
                "current_status","confidence_score","verification_status","confidence_reasons","evidence_json",
                "content_hash","first_seen_at","last_seen_at","last_verified_at","consecutive_misses","created_at","updated_at"
            ]
            values = [
                record.get(f) for f in fields[:]
            ]
            values[fields.index("first_seen_at")] = now
            values[fields.index("last_seen_at")] = now
            values[fields.index("last_verified_at")] = now
            values[fields.index("created_at")] = now
            values[fields.index("updated_at")] = now
            values[fields.index("consecutive_misses")] = 0
            placeholders = ",".join("?" for _ in fields)
            conn.execute(f"INSERT INTO scholarships ({','.join(fields)}) VALUES ({placeholders})", values)
            new_id = conn.execute("SELECT id FROM scholarships WHERE fingerprint=?", (fingerprint,)).fetchone()[0]
            return {"action": "created", "id": new_id, "changes": []}

        scholarship_id = old["id"]
        changes = []
        for field in TRACKED_FIELDS:
            new_value = record.get(field)
            old_value = old[field]
            if new_value is None:
                continue
            if str(old_value) != str(new_value):
                evidence = record.get("evidence", {}).get(field, {})
                snippet = evidence.get("snippet") if isinstance(evidence, dict) else None
                conn.execute("""
                    INSERT INTO change_log(scholarship_id,field_name,old_value,new_value,detected_at,source_url,evidence)
                    VALUES(?,?,?,?,?,?,?)
                """, (scholarship_id, field, str(old_value), str(new_value), now,
                      record.get("official_source_url", old["official_source_url"]), snippet or "Current source fetched; see evidence_json"))
                changes.append({"field": field, "old": old_value, "new": new_value})
        update_fields = [
            "name","provider","official_source_url","application_url","source_type","amount_benefit","eligibility",
            "academic_requirements","education_level","income_criteria","age_criteria","gender_criteria",
            "category_criteria","domicile_criteria","institution_criteria","opening_date","closing_date",
            "documents_required","selection_process","renewal_requirements","current_status","confidence_score",
            "verification_status","confidence_reasons","evidence_json","content_hash"
        ]
        assignments = [f"{f}=?" for f in update_fields]
        values = [record.get(f, old[f]) for f in update_fields]
        assignments.extend(["last_seen_at=?", "last_verified_at=?", "updated_at=?", "consecutive_misses=0"])
        values.extend([now, now, now, fingerprint])
        conn.execute(f"UPDATE scholarships SET {','.join(assignments)} WHERE fingerprint=?", values)
        return {"action": "updated" if changes else "unchanged", "id": scholarship_id, "changes": changes}

def increment_miss(fingerprint, db_path=None):
    with connect(db_path) as conn:
        row = conn.execute("SELECT id,consecutive_misses FROM scholarships WHERE fingerprint=?", (fingerprint,)).fetchone()
        if not row:
            return
        misses = row["consecutive_misses"] + 1
        status = "NO_LONGER_VERIFIABLE" if misses >= 3 else "REVIEW_REQUIRED"
        conn.execute(
            "UPDATE scholarships SET consecutive_misses=?,current_status=?,updated_at=? WHERE id=?",
            (misses, status, utc_now(), row["id"])
        )


def mark_url_miss(url, db_path=None):
    """Record a failed re-verification for records whose primary source URL was attempted."""
    now = utc_now()
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id, consecutive_misses FROM scholarships WHERE official_source_url=?",
            (url,)
        ).fetchall()
        for row in rows:
            misses = row["consecutive_misses"] + 1
            status = "NO_LONGER_VERIFIABLE" if misses >= 3 else "REVIEW_REQUIRED"
            conn.execute(
                "UPDATE scholarships SET consecutive_misses=?, current_status=?, updated_at=? WHERE id=?",
                (misses, status, now, row["id"])
            )
