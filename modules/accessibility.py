import os
import requests
from bs4 import BeautifulSoup
from modules.http import SESSION


PAGESPEED_API = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


def analyze_accessibility(url: str) -> dict:
    results = {"score": None, "issues": [], "details": {}}

    try:
        r = SESSION.get(url, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        results["issues"].append({"severity": "critical", "msg": f"Could not fetch page: {e}"})
        return results

    # Lang attribute on <html>
    html_tag = soup.find("html")
    if not html_tag or not html_tag.get("lang"):
        results["issues"].append({"severity": "critical", "msg": "Missing lang attribute on <html> tag (WCAG 3.1.1)"})
    else:
        results["issues"].append({"severity": "ok", "msg": f"html lang attribute set: '{html_tag['lang']}'"})

    # Images alt text
    imgs = soup.find_all("img")
    imgs_no_alt = [img for img in imgs if img.get("alt") is None]
    imgs_empty_alt = [img for img in imgs if img.get("alt") == ""]
    decorative = len(imgs_empty_alt)
    if imgs_no_alt:
        results["issues"].append({"severity": "critical", "msg": f"{len(imgs_no_alt)} image(s) missing alt attribute entirely (WCAG 1.1.1)"})
    elif imgs:
        results["issues"].append({"severity": "ok", "msg": f"All {len(imgs)} images have alt attribute ({decorative} decorative with empty alt)"})

    # Form inputs with labels
    inputs = soup.find_all("input", type=lambda t: t not in ("hidden", "submit", "button", "reset", "image"))
    unlabeled = []
    for inp in inputs:
        inp_id = inp.get("id")
        has_label = False
        if inp_id and soup.find("label", attrs={"for": inp_id}):
            has_label = True
        if inp.get("aria-label") or inp.get("aria-labelledby") or inp.get("title") or inp.get("placeholder"):
            has_label = True
        parent = inp.parent
        if parent and parent.name == "label":
            has_label = True
        if not has_label:
            unlabeled.append(inp)
    if unlabeled:
        results["issues"].append({"severity": "critical", "msg": f"{len(unlabeled)} form input(s) without label or aria-label (WCAG 1.3.1)"})
    elif inputs:
        results["issues"].append({"severity": "ok", "msg": f"All {len(inputs)} form inputs have labels"})

    # Buttons with accessible text
    buttons = soup.find_all("button")
    empty_btns = [b for b in buttons if not b.text.strip() and not b.get("aria-label") and not b.get("aria-labelledby") and not b.get("title")]
    if empty_btns:
        results["issues"].append({"severity": "warning", "msg": f"{len(empty_btns)} button(s) have no accessible text (WCAG 4.1.2)"})
    elif buttons:
        results["issues"].append({"severity": "ok", "msg": f"All {len(buttons)} buttons have accessible text"})

    # Links with descriptive text
    links = soup.find_all("a", href=True)
    bad_links = [a for a in links if a.text.strip().lower() in ("click here", "here", "read more", "more", "link") and not a.get("aria-label")]
    if bad_links:
        results["issues"].append({"severity": "warning", "msg": f"{len(bad_links)} link(s) with non-descriptive text like 'click here' (WCAG 2.4.4)"})

    # Empty links
    empty_links = [a for a in links if not a.text.strip() and not a.get("aria-label") and not a.find("img")]
    if empty_links:
        results["issues"].append({"severity": "warning", "msg": f"{len(empty_links)} link(s) with no visible text or aria-label"})

    # Skip navigation link
    skip_link = soup.find("a", href="#main") or soup.find("a", href="#content") or soup.find("a", string=lambda s: s and "skip" in s.lower())
    if not skip_link:
        results["issues"].append({"severity": "info", "msg": "No skip navigation link found (recommended for keyboard users)"})
    else:
        results["issues"].append({"severity": "ok", "msg": "Skip navigation link present"})

    # Heading hierarchy (a11y perspective)
    headings = [int(h.name[1]) for h in soup.find_all(["h1","h2","h3","h4","h5","h6"])]
    if headings and headings[0] != 1:
        results["issues"].append({"severity": "warning", "msg": f"First heading is <h{headings[0]}>, should be <h1> (WCAG 1.3.1)"})

    # ARIA landmarks
    main = soup.find("main") or soup.find(attrs={"role": "main"})
    nav = soup.find("nav") or soup.find(attrs={"role": "navigation"})
    if not main:
        results["issues"].append({"severity": "warning", "msg": "No <main> landmark found (WCAG 1.3.6)"})
    else:
        results["issues"].append({"severity": "ok", "msg": "<main> landmark present"})
    if not nav:
        results["issues"].append({"severity": "info", "msg": "No <nav> landmark found"})

    # tabindex issues
    bad_tabindex = soup.find_all(attrs={"tabindex": lambda v: v and str(v).lstrip("-").isdigit() and int(v) > 0})
    if bad_tabindex:
        results["issues"].append({"severity": "warning", "msg": f"{len(bad_tabindex)} element(s) with positive tabindex (disrupts natural tab order)"})

    # PageSpeed accessibility score
    api_key = os.environ.get("PAGESPEED_API_KEY", "")
    try:
        params = {"url": url, "strategy": "mobile", "category": "accessibility"}
        if api_key:
            params["key"] = api_key
        resp = SESSION.get(PAGESPEED_API, params=params, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            lhr = data.get("lighthouseResult", {})
            score = lhr.get("categories", {}).get("accessibility", {}).get("score")
            if score is not None:
                results["score"] = round(score * 100)

            # Pull failing accessibility audits
            audits = lhr.get("audits", {})
            for audit_id, audit in audits.items():
                s = audit.get("score")
                if s is not None and s < 1 and audit.get("details", {}).get("type") in ("table", "list", "node"):
                    results["issues"].append({
                        "severity": "warning",
                        "msg": f"[Lighthouse] {audit.get('title','')}: {audit.get('description','')[:100]}"
                    })
    except Exception:
        pass

    return results
