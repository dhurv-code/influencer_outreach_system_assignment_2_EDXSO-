import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from config import DB_PATH

def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def connect(db_path=None):
    path = Path(db_path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn



def _migrate_schema(conn):
    """Add missing columns to an existing SQLite database."""

    additions = {
        "scholarships": {
            "fingerprint": "TEXT",
            "name": "TEXT NOT NULL DEFAULT 'Untitled scholarship'",
            "provider": "TEXT NOT NULL DEFAULT 'Not specified'",
            "official_source_url": "TEXT NOT NULL DEFAULT ''",
            "application_url": "TEXT",
            "source_type": "TEXT NOT NULL DEFAULT 'OTHER'",
            "amount_benefit": "TEXT NOT NULL DEFAULT 'Not specified'",
            "eligibility": "TEXT NOT NULL DEFAULT 'Not specified'",
            "academic_requirements": "TEXT NOT NULL DEFAULT 'Not specified'",
            "education_level": "TEXT NOT NULL DEFAULT 'Not specified'",
            "income_criteria": "TEXT NOT NULL DEFAULT 'Not specified'",
            "age_criteria": "TEXT NOT NULL DEFAULT 'Not specified'",
            "gender_criteria": "TEXT NOT NULL DEFAULT 'Not specified'",
            "category_criteria": "TEXT NOT NULL DEFAULT 'Not specified'",
            "domicile_criteria": "TEXT NOT NULL DEFAULT 'Not specified'",
            "institution_criteria": "TEXT NOT NULL DEFAULT 'Not specified'",
            "opening_date": "TEXT NOT NULL DEFAULT 'Not specified'",
            "closing_date": "TEXT NOT NULL DEFAULT 'Not specified'",
            "documents_required": "TEXT NOT NULL DEFAULT 'Not specified'",
            "selection_process": "TEXT NOT NULL DEFAULT 'Not specified'",
            "renewal_requirements": "TEXT NOT NULL DEFAULT 'Not specified'",
            "current_status": "TEXT NOT NULL DEFAULT 'REVIEW_REQUIRED'",
            "confidence_score": "REAL NOT NULL DEFAULT 0",
            "verification_status": "TEXT NOT NULL DEFAULT 'REVIEW REQUIRED'",
            "confidence_reasons": "TEXT NOT NULL DEFAULT '[]'",
            "evidence_json": "TEXT NOT NULL DEFAULT '{}'",
            "content_hash": "TEXT NOT NULL DEFAULT ''",
            "first_seen_at": "TEXT NOT NULL DEFAULT ''",
            "last_seen_at": "TEXT NOT NULL DEFAULT ''",
            "last_verified_at": "TEXT",
            "consecutive_misses": "INTEGER NOT NULL DEFAULT 0",
            "created_at": "TEXT NOT NULL DEFAULT ''",
            "updated_at": "TEXT NOT NULL DEFAULT ''",
        },
        "crawl_runs": {
            "started_at": "TEXT NOT NULL DEFAULT ''",
            "finished_at": "TEXT",
            "discovered_count": "INTEGER DEFAULT 0",
            "crawled_count": "INTEGER DEFAULT 0",
            "records_created": "INTEGER DEFAULT 0",
            "records_updated": "INTEGER DEFAULT 0",
            "errors_count": "INTEGER DEFAULT 0",
            "notes": "TEXT"
        }
    }

    for table, columns in additions.items():
        existing = {
            row["name"]
            for row in conn.execute(
                f"PRAGMA table_info({table})"
            ).fetchall()
        }

        for column, definition in columns.items():
            if column not in existing:
                conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN "
                    f"{column} {definition}"
                )



def init_db(db_path=None):
    with connect(db_path) as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS crawl_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL DEFAULT '',
            finished_at TEXT,
            discovered_count INTEGER DEFAULT 0,
            crawled_count INTEGER DEFAULT 0,
            records_created INTEGER DEFAULT 0,
            records_updated INTEGER DEFAULT 0,
            errors_count INTEGER DEFAULT 0,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS scholarships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint TEXT UNIQUE,
            name TEXT NOT NULL DEFAULT 'Untitled scholarship',
            provider TEXT NOT NULL DEFAULT 'Not specified',
            official_source_url TEXT NOT NULL DEFAULT '',
            application_url TEXT,
            source_type TEXT NOT NULL DEFAULT 'OTHER',
            amount_benefit TEXT NOT NULL DEFAULT 'Not specified',
            eligibility TEXT NOT NULL DEFAULT 'Not specified',
            academic_requirements TEXT NOT NULL DEFAULT 'Not specified',
            education_level TEXT NOT NULL DEFAULT 'Not specified',
            income_criteria TEXT NOT NULL DEFAULT 'Not specified',
            age_criteria TEXT NOT NULL DEFAULT 'Not specified',
            gender_criteria TEXT NOT NULL DEFAULT 'Not specified',
            category_criteria TEXT NOT NULL DEFAULT 'Not specified',
            domicile_criteria TEXT NOT NULL DEFAULT 'Not specified',
            institution_criteria TEXT NOT NULL DEFAULT 'Not specified',
            opening_date TEXT NOT NULL DEFAULT 'Not specified',
            closing_date TEXT NOT NULL DEFAULT 'Not specified',
            documents_required TEXT NOT NULL DEFAULT 'Not specified',
            selection_process TEXT NOT NULL DEFAULT 'Not specified',
            renewal_requirements TEXT NOT NULL DEFAULT 'Not specified',
            current_status TEXT NOT NULL DEFAULT 'REVIEW_REQUIRED',
            confidence_score REAL NOT NULL DEFAULT 0,
            verification_status TEXT NOT NULL DEFAULT 'REVIEW REQUIRED',
            confidence_reasons TEXT NOT NULL DEFAULT '[]',
            evidence_json TEXT NOT NULL DEFAULT '{}',
            content_hash TEXT NOT NULL DEFAULT '',
            first_seen_at TEXT NOT NULL DEFAULT '',
            last_seen_at TEXT NOT NULL DEFAULT '',
            last_verified_at TEXT,
            consecutive_misses INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS change_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scholarship_id INTEGER NOT NULL,
            field_name TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            detected_at TEXT NOT NULL,
            source_url TEXT NOT NULL,
            evidence TEXT,
            FOREIGN KEY(scholarship_id)
                REFERENCES scholarships(id)
        );

        CREATE TABLE IF NOT EXISTS crawl_errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            error TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            run_id INTEGER,
            FOREIGN KEY(run_id) REFERENCES crawl_runs(id)
        );
        """)

        # Add columns missing from an older database.
        _migrate_schema(conn)

        # Create indexes only after migration.
        conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_scholarships_status
            ON scholarships(current_status);

        CREATE INDEX IF NOT EXISTS idx_scholarships_verification
            ON scholarships(verification_status);

        CREATE INDEX IF NOT EXISTS idx_scholarships_name
            ON scholarships(name);

        CREATE INDEX IF NOT EXISTS idx_change_log_scholarship
            ON change_log(scholarship_id);
        """)

    return True


def row_to_dict(row):
    return dict(row) if row else None

def list_scholarships(db_path=None, search_text="", status="All", limit=500):
    with connect(db_path) as conn:
        query = "SELECT * FROM scholarships WHERE 1=1"
        params = []
        if search_text:
            query += " AND (name LIKE ? OR provider LIKE ? OR eligibility LIKE ?)"
            pattern = f"%{search_text}%"
            params.extend([pattern, pattern, pattern])
        if status != "All":
            query += " AND current_status = ?"
            params.append(status)
        query += " ORDER BY confidence_score DESC, updated_at DESC LIMIT ?"
        params.append(int(limit))
        return [dict(r) for r in conn.execute(query, params).fetchall()]

def get_scholarship(scholarship_id, db_path=None):
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM scholarships WHERE id=?", (scholarship_id,)).fetchone()
        return row_to_dict(row)

def get_change_history(scholarship_id, db_path=None):
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM change_log WHERE scholarship_id=? ORDER BY detected_at DESC",
            (scholarship_id,)
        ).fetchall()
        return [dict(r) for r in rows]

def dashboard_metrics(db_path=None):
    with connect(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM scholarships").fetchone()[0]
        verified = conn.execute(
            "SELECT COUNT(*) FROM scholarships WHERE verification_status='VERIFIED'"
        ).fetchone()[0]
        review = conn.execute(
            "SELECT COUNT(*) FROM scholarships WHERE verification_status='REVIEW REQUIRED'"
        ).fetchone()[0]
        active = conn.execute(
            "SELECT COUNT(*) FROM scholarships WHERE current_status IN ('ACTIVE','EXPIRING_SOON')"
        ).fetchone()[0]
        expired = conn.execute(
            "SELECT COUNT(*) FROM scholarships WHERE current_status='EXPIRED'"
        ).fetchone()[0]
        avg = conn.execute("SELECT AVG(confidence_score) FROM scholarships").fetchone()[0] or 0
        recently_updated = conn.execute(
            "SELECT COUNT(*) FROM scholarships WHERE updated_at >= datetime('now','-7 days')"
        ).fetchone()[0]
        return {
            "total": total, "verified": verified, "review_required": review,
            "active": active, "expired": expired, "average_confidence": round(avg, 2),
            "recently_updated": recently_updated
        }

def record_error(url, error, run_id=None, db_path=None):
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO crawl_errors(url,error,occurred_at,run_id) VALUES(?,?,?,?)",
            (url, str(error)[:1500], utc_now(), run_id)
        )


