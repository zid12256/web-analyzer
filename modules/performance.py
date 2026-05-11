import time
import os
import requests
from modules.http import SESSION


PAGESPEED_API = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


def analyze_performance(url: str) -> dict:
    results = {
        "score": None,
        "ttfb_ms": None,
        "metrics": {},
        "opportunities": [],
        "diagnostics": [],
        "issues": [],
        "raw": {}
    }

    # Direct TTFB measurement
    try:
        start = time.time()
        r = SESSION.get(url, timeout=15)
        ttfb = round((time.time() - start) * 1000)
        results["ttfb_ms"] = ttfb
        if ttfb > 600:
            results["issues"].append({"severity": "critical", "msg": f"High TTFB: {ttfb}ms (target < 200ms)"})
        elif ttfb > 300:
            results["issues"].append({"severity": "warning", "msg": f"Slow TTFB: {ttfb}ms (target < 200ms)"})
        else:
            results["issues"].append({"severity": "ok", "msg": f"Good TTFB: {ttfb}ms"})
    except Exception as e:
        results["issues"].append({"severity": "critical", "msg": f"Site unreachable: {e}"})
        return results

    # PageSpeed Insights API
    api_key = os.environ.get("PAGESPEED_API_KEY", "")
    for strategy in ("mobile", "desktop"):
        params = {"url": url, "strategy": strategy, "category": "performance"}
        if api_key:
            params["key"] = api_key
        try:
            resp = SESSION.get(PAGESPEED_API, params=params, timeout=30)
            if resp.status_code != 200:
                results["issues"].append({"severity": "warning", "msg": f"PageSpeed API error ({strategy}): {resp.status_code}"})
                continue

            data = resp.json()
            lhr = data.get("lighthouseResult", {})
            cats = lhr.get("categories", {})
            audits = lhr.get("audits", {})

            score = cats.get("performance", {}).get("score")
            if score is not None:
                score = round(score * 100)
                results["score"] = score if strategy == "mobile" else results.get("score", score)
                results["raw"][f"{strategy}_score"] = score

            # Core Web Vitals
            metric_keys = {
                "first-contentful-paint": "FCP",
                "largest-contentful-paint": "LCP",
                "total-blocking-time": "TBT",
                "cumulative-layout-shift": "CLS",
                "speed-index": "Speed Index",
                "interactive": "TTI",
            }
            for key, label in metric_keys.items():
                audit = audits.get(key, {})
                display = audit.get("displayValue", "N/A")
                rating = audit.get("score")
                if rating is not None:
                    if rating < 0.5:
                        sev = "critical"
                    elif rating < 0.9:
                        sev = "warning"
                    else:
                        sev = "ok"
                else:
                    sev = "info"
                if strategy == "mobile":
                    results["metrics"][label] = {"value": display, "severity": sev}

            # Opportunities (potential savings)
            for audit_id, audit in audits.items():
                if audit.get("details", {}).get("type") == "opportunity":
                    savings = audit.get("details", {}).get("overallSavingsMs", 0)
                    if savings and savings > 100 and strategy == "mobile":
                        results["opportunities"].append({
                            "title": audit.get("title", audit_id),
                            "savings_ms": round(savings),
                            "description": audit.get("description", ""),
                        })

            # Diagnostics with warnings
            for audit_id, audit in audits.items():
                if audit.get("score") is not None and audit["score"] < 0.9:
                    if audit.get("details", {}).get("type") in ("table", "list") and strategy == "mobile":
                        results["diagnostics"].append({
                            "title": audit.get("title", audit_id),
                            "description": audit.get("description", ""),
                            "score": audit["score"],
                        })

        except Exception as e:
            results["issues"].append({"severity": "warning", "msg": f"PageSpeed API failed ({strategy}): {e}"})

    # Interpret score
    score = results.get("score")
    if score is not None:
        if score < 50:
            results["issues"].append({"severity": "critical", "msg": f"Poor performance score: {score}/100"})
        elif score < 90:
            results["issues"].append({"severity": "warning", "msg": f"Performance needs improvement: {score}/100"})
        else:
            results["issues"].append({"severity": "ok", "msg": f"Good performance score: {score}/100"})

    return results
