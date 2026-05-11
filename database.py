"""
SQLite database for storing analysis history.
"""
import sqlite3
import json
import os
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "history.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            overall_score INTEGER,
            performance_score INTEGER,
            seo_score INTEGER,
            accessibility_score INTEGER,
            security_score INTEGER,
            critical_count INTEGER DEFAULT 0,
            warning_count INTEGER DEFAULT 0,
            ok_count INTEGER DEFAULT 0,
            results_json TEXT NOT NULL
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_url ON analyses(url)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON analyses(timestamp)")
    conn.commit()
    conn.close()


def count_severities(results: dict) -> dict:
    """Count critical/warning/ok issues across all sections."""
    counts = {"critical": 0, "warning": 0, "ok": 0, "info": 0}
    for section_data in results.values():
        if isinstance(section_data, dict):
            for issue in section_data.get("issues", []):
                sev = issue.get("severity", "info")
                if sev in counts:
                    counts[sev] += 1
    return counts


def overall_score(results: dict):
    """Compute weighted overall score."""
    weights = {"performance": 0.3, "seo": 0.25, "accessibility": 0.25, "security": 0.2}
    total = 0
    total_w = 0
    for key, w in weights.items():
        s = results.get(key, {}).get("score")
        if s is not None:
            total += s * w
            total_w += w
    return round(total / total_w) if total_w else None


def save_analysis(url: str, results: dict) -> int:
    """Save analysis to DB and return its ID."""
    init_db()
    conn = get_conn()
    cur = conn.cursor()
    sevs = count_severities(results)
    cur.execute("""
        INSERT INTO analyses
        (url, timestamp, overall_score, performance_score, seo_score,
         accessibility_score, security_score, critical_count, warning_count,
         ok_count, results_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        url,
        datetime.utcnow().isoformat(),
        overall_score(results),
        results.get("performance", {}).get("score"),
        results.get("seo", {}).get("score"),
        results.get("accessibility", {}).get("score"),
        results.get("security", {}).get("score"),
        sevs["critical"],
        sevs["warning"],
        sevs["ok"],
        json.dumps(results, default=str),
    ))
    conn.commit()
    analysis_id = cur.lastrowid
    conn.close()
    return analysis_id


def list_analyses(limit: int = 50, url_filter: str = None):
    """List recent analyses (without full results)."""
    init_db()
    conn = get_conn()
    cur = conn.cursor()
    if url_filter:
        cur.execute("""
            SELECT id, url, timestamp, overall_score, performance_score,
                   seo_score, accessibility_score, security_score,
                   critical_count, warning_count
            FROM analyses WHERE url LIKE ?
            ORDER BY timestamp DESC LIMIT ?
        """, (f"%{url_filter}%", limit))
    else:
        cur.execute("""
            SELECT id, url, timestamp, overall_score, performance_score,
                   seo_score, accessibility_score, security_score,
                   critical_count, warning_count
            FROM analyses ORDER BY timestamp DESC LIMIT ?
        """, (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_analysis(analysis_id: int):
    """Get full analysis details by ID."""
    init_db()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    data = dict(row)
    data["results"] = json.loads(data["results_json"])
    return data


def delete_analysis(analysis_id: int) -> bool:
    init_db()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM analyses WHERE id = ?", (analysis_id,))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def history_for_url(url: str, limit: int = 20):
    """Get history for a specific URL for time-series charts."""
    init_db()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, timestamp, overall_score, performance_score, seo_score,
               accessibility_score, security_score
        FROM analyses WHERE url = ?
        ORDER BY timestamp ASC LIMIT ?
    """, (url, limit))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows
