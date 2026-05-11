#!/usr/bin/env python3
"""
Web UI for the Web Analyzer — Flask app.
Run: python3 app.py  →  http://127.0.0.1:5000
"""
import os
import json
import threading
import uuid
from datetime import datetime
from pathlib import Path

from flask import (
    Flask, render_template, request, jsonify, send_file,
    redirect, url_for, abort,
)

from modules.performance import analyze_performance
from modules.seo import analyze_seo
from modules.accessibility import analyze_accessibility
from modules.security import analyze_security
from modules.links import analyze_links

import database as db
import exporters

BASE_DIR = Path(__file__).parent
EXPORTS_DIR = BASE_DIR / "exports"
EXPORTS_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

# Background job tracking
JOBS = {}
JOBS_LOCK = threading.Lock()

SECTIONS = ["performance", "seo", "accessibility", "security", "links"]
MODULE_MAP = {
    "performance": analyze_performance,
    "seo": analyze_seo,
    "accessibility": analyze_accessibility,
    "security": analyze_security,
    "links": analyze_links,
}


def validate_url(url: str) -> str:
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def run_job(job_id: str, url: str, sections: list):
    """Run analysis in background and update JOBS dict."""
    results = {}
    total = len(sections)
    for i, section in enumerate(sections):
        with JOBS_LOCK:
            JOBS[job_id]["current"] = section
            JOBS[job_id]["progress"] = round((i / total) * 100)
        try:
            fn = MODULE_MAP[section]
            results[section] = fn(url)
        except Exception as e:
            results[section] = {
                "issues": [{"severity": "critical", "msg": f"Module crashed: {e}"}]
            }
        with JOBS_LOCK:
            JOBS[job_id]["partial"] = results.copy()

    # Save to history
    try:
        analysis_id = db.save_analysis(url, results)
    except Exception:
        analysis_id = None

    with JOBS_LOCK:
        JOBS[job_id]["status"] = "done"
        JOBS[job_id]["progress"] = 100
        JOBS[job_id]["results"] = results
        JOBS[job_id]["analysis_id"] = analysis_id
        JOBS[job_id]["url"] = url


# ----------------------------- Routes -----------------------------

@app.route("/")
def index():
    recent = db.list_analyses(limit=10)
    return render_template("index.html", recent=recent)


@app.route("/analyze", methods=["POST"])
def start_analysis():
    url = validate_url(request.form.get("url", ""))
    if not url or url == "https://":
        return jsonify({"error": "URL required"}), 400

    selected = request.form.getlist("sections")
    if not selected:
        selected = SECTIONS

    job_id = str(uuid.uuid4())
    with JOBS_LOCK:
        JOBS[job_id] = {
            "status": "running",
            "url": url,
            "sections": selected,
            "current": selected[0] if selected else "",
            "progress": 0,
            "started": datetime.utcnow().isoformat(),
        }
    t = threading.Thread(target=run_job, args=(job_id, url, selected), daemon=True)
    t.start()
    return jsonify({"job_id": job_id})


@app.route("/job/<job_id>")
def job_status(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        return jsonify({
            "status": job["status"],
            "progress": job.get("progress", 0),
            "current": job.get("current", ""),
            "url": job.get("url"),
            "analysis_id": job.get("analysis_id"),
        })


@app.route("/results/<int:analysis_id>")
def view_results(analysis_id):
    record = db.get_analysis(analysis_id)
    if not record:
        abort(404)
    history = db.history_for_url(record["url"], limit=20)
    return render_template(
        "results.html",
        analysis_id=analysis_id,
        url=record["url"],
        timestamp=record["timestamp"],
        overall=record["overall_score"],
        results=record["results"],
        history=history,
    )


@app.route("/history")
def history():
    q = request.args.get("q", "").strip() or None
    rows = db.list_analyses(limit=200, url_filter=q)
    return render_template("history.html", rows=rows, q=q or "")


@app.route("/history/delete/<int:analysis_id>", methods=["POST"])
def history_delete(analysis_id):
    db.delete_analysis(analysis_id)
    return redirect(url_for("history"))


@app.route("/compare")
def compare_page():
    ids_str = request.args.get("ids", "")
    ids = [int(x) for x in ids_str.split(",") if x.strip().isdigit()] if ids_str else []
    records = []
    for aid in ids:
        rec = db.get_analysis(aid)
        if rec:
            records.append(rec)
    rows = db.list_analyses(limit=100)
    return render_template("compare.html", records=records, all_rows=rows, selected_ids=ids)


@app.route("/export/<int:analysis_id>/<fmt>")
def export(analysis_id, fmt):
    record = db.get_analysis(analysis_id)
    if not record:
        abort(404)

    url = record["url"]
    results = record["results"]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    host = url.replace("https://", "").replace("http://", "").split("/")[0].replace(".", "_")
    base_name = f"report_{host}_{ts}"

    if fmt == "json":
        path = EXPORTS_DIR / f"{base_name}.json"
        path.write_text(json.dumps({"url": url, "results": results}, indent=2, default=str))
        return send_file(path, as_attachment=True)
    elif fmt == "csv":
        path = EXPORTS_DIR / f"{base_name}.csv"
        exporters.export_csv(url, results, str(path))
        return send_file(path, as_attachment=True)
    elif fmt == "xlsx":
        path = EXPORTS_DIR / f"{base_name}.xlsx"
        exporters.export_xlsx(url, results, str(path))
        return send_file(path, as_attachment=True)
    elif fmt == "pdf":
        from pdf_reporter import generate_pdf
        path = EXPORTS_DIR / f"{base_name}.pdf"
        generate_pdf(url, results, output_path=str(path))
        return send_file(path, as_attachment=True)
    else:
        abort(400)


@app.route("/api/history/<path:url>")
def api_history_for_url(url):
    """Returns the time-series score history for charts."""
    rows = db.history_for_url(url, limit=50)
    return jsonify(rows)


if __name__ == "__main__":
    db.init_db()
    port = int(os.environ.get("PORT", 5000))
    print(f"\n  Web Analyzer UI running at: http://127.0.0.1:{port}\n")
    app.run(host="127.0.0.1", port=port, debug=False)
