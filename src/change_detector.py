import json

from src.database import connect, utc_now

TRACKED_FIELDS = [
    "name", "provider", "application_url", "amount_benefit", "eligibility",
    "academic_requirements", "education_level", "income_criteria", "age_criteria",
    "gender_criteria", "category_criteria", "domicile_criteria", "institution_criteria",
    "opening_date", "closing_date", "documents_required", "selection_process",
    "renewal_requirements", "current_status", "verification_status", "confidence_score",
]

MISSING_VALUES = {None, "", "Not specified", "N/A", "Unknown"}


def _is_missing(value):
    return value in MISSING_VALUES if isinstance(value, str) or value is None else False


def save_or_update(record, db_path=None, run_id=None):
    """Insert or update a record and retain old/new values for every meaningful change."""
    fingerprint = record.get("fingerprint")
    if not fingerprint:
        raise ValueError("A stable fingerprint is required before saving a scholarship")

    now = utc_now()
    is_verified = record.get("verification_status") == "VERIFIED"
    source_url = record.get("source_url") or record.get("official_source_url") or ""
    official_url = record.get("official_source_url") or ""
    evidence = record.get("evidence") or {}
    evidence_json = record.get("evidence_json") or json.dumps(evidence, ensure_ascii=False)
    reasons_json = record.get("confidence_reasons") or "[]"
    if not isinstance(reasons_json, str):
        reasons_json = json.dumps(reasons_json, ensure_ascii=False)
    if not isinstance(evidence_json, str):
        evidence_json = json.dumps(evidence_json, ensure_ascii=False)

    with connect(db_path) as conn:
        old = conn.execute("SELECT * FROM scholarships WHERE fingerprint=?", (fingerprint,)).fetchone()
        if old is None:
            fields = [
                "fingerprint", "source_url", "source_is_official", "name", "provider", "official_source_url",
                "application_url", "source_type", "amount_benefit", "eligibility", "academic_requirements",
                "education_level", "income_criteria", "age_criteria", "gender_criteria", "category_criteria",
                "domicile_criteria", "institution_criteria", "opening_date", "closing_date", "documents_required",
                "selection_process", "renewal_requirements", "current_status", "confidence_score",
                "verification_status", "confidence_reasons", "evidence_json", "content_hash", "first_seen_at",
                "last_seen_at", "last_verified_at", "consecutive_misses", "created_at", "updated_at",
            ]
            values_by_field = {
                **record,
                "source_url": source_url,
                "source_is_official": int(bool(record.get("source_is_official"))),
                "official_source_url": official_url,
                "confidence_reasons": reasons_json,
                "evidence_json": evidence_json,
                "first_seen_at": now,
                "last_seen_at": now,
                "last_verified_at": now if is_verified else None,
                "consecutive_misses": 0,
                "created_at": now,
                "updated_at": now,
            }
            values = [values_by_field.get(field) for field in fields]
            cursor = conn.execute(
                f"INSERT INTO scholarships ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})",
                values,
            )
            return {"action": "created", "id": cursor.lastrowid, "changes": []}

        scholarship_id = old["id"]
        # If a later page version no longer exposes a field, do not erase previously sourced data.
        # The new status/evidence still indicates that it should be reviewed.
        merged = dict(record)
        merged["source_url"] = source_url or old["source_url"]
        merged["official_source_url"] = official_url if bool(record.get("source_is_official")) else ""
        merged_evidence = dict(evidence)
        for field in (
            "name", "provider", "amount_benefit", "eligibility", "academic_requirements", "education_level",
            "income_criteria", "age_criteria", "gender_criteria", "category_criteria", "domicile_criteria",
            "institution_criteria", "opening_date", "closing_date", "documents_required", "selection_process",
            "renewal_requirements",
        ):
            new_value = record.get(field)
            old_value = old[field]
            if _is_missing(new_value) and not _is_missing(old_value):
                merged[field] = old_value
                try:
                    old_evidence = json.loads(old["evidence_json"] or "{}")
                except (TypeError, json.JSONDecodeError):
                    old_evidence = {}
                if field in old_evidence and field not in merged_evidence:
                    merged_evidence[field] = old_evidence[field]
        merged["evidence_json"] = json.dumps(merged_evidence, ensure_ascii=False)

        changes = []
        for field in TRACKED_FIELDS:
            new_value = merged.get(field)
            old_value = old[field]
            if new_value is None or str(old_value) == str(new_value):
                continue
            field_evidence = evidence.get(field, {})
            snippet = field_evidence.get("snippet") if isinstance(field_evidence, dict) else None
            conn.execute(
                """INSERT INTO change_log
                   (scholarship_id,field_name,old_value,new_value,detected_at,source_url,evidence)
                   VALUES(?,?,?,?,?,?,?)""",
                (
                    scholarship_id, field, str(old_value), str(new_value), now,
                    source_url or old["source_url"] or official_url,
                    snippet or "See field-level evidence retained with this record",
                ),
            )
            changes.append({"field": field, "old": old_value, "new": new_value})

        update_fields = [
            "source_url", "source_is_official", "name", "provider", "official_source_url", "application_url",
            "source_type", "amount_benefit", "eligibility", "academic_requirements", "education_level",
            "income_criteria", "age_criteria", "gender_criteria", "category_criteria", "domicile_criteria",
            "institution_criteria", "opening_date", "closing_date", "documents_required", "selection_process",
            "renewal_requirements", "current_status", "confidence_score", "verification_status",
            "confidence_reasons", "evidence_json", "content_hash",
        ]
        assignments = [f"{field}=?" for field in update_fields]
        values = []
        for field in update_fields:
            if field == "source_is_official":
                values.append(int(bool(record.get(field))))
            elif field == "confidence_reasons":
                values.append(reasons_json)
            elif field == "evidence_json":
                values.append(merged["evidence_json"])
            else:
                values.append(merged.get(field, old[field]))
        assignments.extend(["last_seen_at=?", "last_verified_at=?", "updated_at=?", "consecutive_misses=0"])
        values.extend([now, now if is_verified else old["last_verified_at"], now, fingerprint])
        conn.execute(f"UPDATE scholarships SET {','.join(assignments)} WHERE fingerprint=?", values)
        return {"action": "updated" if changes else "unchanged", "id": scholarship_id, "changes": changes}


def increment_miss(fingerprint, db_path=None):
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT id,source_url,current_status,consecutive_misses FROM scholarships WHERE fingerprint=?",
            (fingerprint,),
        ).fetchone()
        if not row:
            return
        misses = row["consecutive_misses"] + 1
        status = "NO_LONGER_VERIFIABLE" if misses >= 3 else "REVIEW_REQUIRED"
        now = utc_now()
        if row["current_status"] != status:
            conn.execute(
                """INSERT INTO change_log
                   (scholarship_id,field_name,old_value,new_value,detected_at,source_url,evidence)
                   VALUES(?,?,?,?,?,?,?)""",
                (row["id"], "current_status", row["current_status"], status, now,
                 row["source_url"] or "", f"Source verification failed; consecutive misses: {misses}"),
            )
        conn.execute(
            """UPDATE scholarships SET consecutive_misses=?,current_status=?,
               verification_status='REVIEW REQUIRED',updated_at=? WHERE id=?""",
            (misses, status, now, row["id"]),
        )


def mark_url_miss(url, db_path=None):
    """Log failed source re-verification; after three misses, mark not verifiable, not expired."""
    now = utc_now()
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT id,source_url,current_status,consecutive_misses FROM scholarships WHERE source_url=? OR official_source_url=?",
            (url, url),
        ).fetchall()
        for row in rows:
            misses = row["consecutive_misses"] + 1
            status = "NO_LONGER_VERIFIABLE" if misses >= 3 else "REVIEW_REQUIRED"
            if row["current_status"] != status:
                conn.execute(
                    """INSERT INTO change_log
                       (scholarship_id,field_name,old_value,new_value,detected_at,source_url,evidence)
                       VALUES(?,?,?,?,?,?,?)""",
                    (row["id"], "current_status", row["current_status"], status, now,
                     row["source_url"] or url, f"Source verification failed; consecutive misses: {misses}"),
                )
            conn.execute(
                """UPDATE scholarships
                   SET consecutive_misses=?,current_status=?,verification_status='REVIEW REQUIRED',updated_at=?
                   WHERE id=?""",
                (misses, status, now, row["id"]),
            )
