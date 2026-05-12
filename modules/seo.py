import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from modules.http import SESSION


PAGESPEED_API = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


def analyze_seo(url: str) -> dict:
    results = {"score": None, "issues": [], "details": {}}

    try:
        r = SESSION.get(url, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        results["issues"].append({"severity": "critical", "msg": f"Could not fetch page: {e}"})
        return results

    # Title
    title_tag = soup.find("title")
    if not title_tag or not title_tag.text.strip():
        results["issues"].append({"severity": "critical", "msg": "Missing <title> tag"})
    else:
        title = title_tag.text.strip()
        results["details"]["title"] = title
        if len(title) < 30:
            results["issues"].append({"severity": "warning", "msg": f"Title too short ({len(title)} chars, ideal 50-60): '{title}'"})
        elif len(title) > 60:
            results["issues"].append({"severity": "warning", "msg": f"Title too long ({len(title)} chars, ideal 50-60): '{title[:50]}...'"})
        else:
            results["issues"].append({"severity": "ok", "msg": f"Good title length ({len(title)} chars)"})

    # Meta description
    meta_desc = soup.find("meta", attrs={"name": "description"})
    if not meta_desc or not meta_desc.get("content", "").strip():
        results["issues"].append({"severity": "critical", "msg": "Missing meta description"})
    else:
        desc = meta_desc["content"].strip()
        results["details"]["meta_description"] = desc
        if len(desc) < 70:
            results["issues"].append({"severity": "warning", "msg": f"Meta description too short ({len(desc)} chars, ideal 150-160)"})
        elif len(desc) > 160:
            results["issues"].append({"severity": "warning", "msg": f"Meta description too long ({len(desc)} chars, ideal 150-160)"})
        else:
            results["issues"].append({"severity": "ok", "msg": f"Good meta description length ({len(desc)} chars)"})

    # H1
    h1_tags = soup.find_all("h1")
    if not h1_tags:
        results["issues"].append({"severity": "critical", "msg": "No <h1> tag found"})
    elif len(h1_tags) > 1:
        results["issues"].append({"severity": "warning", "msg": f"Multiple <h1> tags found ({len(h1_tags)}), should have only one"})
    else:
        results["issues"].append({"severity": "ok", "msg": f"Single <h1> present: '{h1_tags[0].text.strip()[:60]}'"})

    # Heading hierarchy
    headings = [(int(h.name[1]), h.text.strip()[:50]) for h in soup.find_all(["h1","h2","h3","h4","h5","h6"])]
    results["details"]["headings"] = headings
    for i in range(1, len(headings)):
        if headings[i][0] > headings[i-1][0] + 1:
            results["issues"].append({"severity": "warning", "msg": f"Skipped heading level: h{headings[i-1][0]} → h{headings[i][0]}"})
            break

    # Canonical
    canonical = soup.find("link", attrs={"rel": "canonical"})
    if not canonical:
        results["issues"].append({"severity": "warning", "msg": "No canonical URL tag found"})
    else:
        results["details"]["canonical"] = canonical.get("href", "")
        results["issues"].append({"severity": "ok", "msg": f"Canonical URL set: {canonical.get('href','')[:60]}"})

    # Open Graph
    og_title = soup.find("meta", property="og:title")
    og_desc = soup.find("meta", property="og:description")
    og_image = soup.find("meta", property="og:image")
    if not og_title:
        results["issues"].append({"severity": "warning", "msg": "Missing og:title (Open Graph)"})
    if not og_desc:
        results["issues"].append({"severity": "warning", "msg": "Missing og:description (Open Graph)"})
    if not og_image:
        results["issues"].append({"severity": "warning", "msg": "Missing og:image (Open Graph / social sharing)"})
    if og_title and og_desc and og_image:
        results["issues"].append({"severity": "ok", "msg": "Open Graph tags present (og:title, og:description, og:image)"})

    # Twitter Card
    tw_card = soup.find("meta", attrs={"name": "twitter:card"})
    if not tw_card:
        results["issues"].append({"severity": "info", "msg": "No Twitter Card meta tags found"})

    # Images alt text (SEO perspective)
    imgs = soup.find_all("img")
    imgs_no_alt = [img for img in imgs if not img.get("alt")]
    if imgs_no_alt:
        results["issues"].append({"severity": "warning", "msg": f"{len(imgs_no_alt)}/{len(imgs)} images missing alt text (SEO + accessibility)"})
    elif imgs:
        results["issues"].append({"severity": "ok", "msg": f"All {len(imgs)} images have alt text"})

    # Robots.txt
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    try:
        rb = SESSION.get(f"{base}/robots.txt", timeout=10)
        if rb.status_code == 200:
            results["details"]["robots_txt"] = True
            results["issues"].append({"severity": "ok", "msg": "robots.txt found"})
        else:
            results["issues"].append({"severity": "warning", "msg": "No robots.txt found"})
    except Exception:
        results["issues"].append({"severity": "warning", "msg": "Could not check robots.txt"})

    # Sitemap
    for sitemap_path in ["/sitemap.xml", "/sitemap_index.xml"]:
        try:
            sm = SESSION.get(f"{base}{sitemap_path}", timeout=10)
            if sm.status_code == 200:
                results["details"]["sitemap"] = f"{base}{sitemap_path}"
                results["issues"].append({"severity": "ok", "msg": f"Sitemap found: {sitemap_path}"})
                break
        except Exception:
            pass
    else:
        results["issues"].append({"severity": "warning", "msg": "No sitemap.xml found"})

    # Structured data (JSON-LD)
    json_ld = soup.find_all("script", attrs={"type": "application/ld+json"})
    if json_ld:
        results["issues"].append({"severity": "ok", "msg": f"Structured data (JSON-LD) found ({len(json_ld)} block(s))"})
    else:
        results["issues"].append({"severity": "info", "msg": "No structured data (JSON-LD) found"})

    # PageSpeed SEO score
    api_key = os.environ.get("PAGESPEED_API_KEY", "")
    try:
        params = {"url": url, "strategy": "mobile", "category": "seo"}
        if api_key:
            params["key"] = api_key
        resp = SESSION.get(PAGESPEED_API, params=params, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            score = data.get("lighthouseResult", {}).get("categories", {}).get("seo", {}).get("score")
            if score is not None:
                results["score"] = round(score * 100)
    except Exception:
        pass

    # Fallback score from own checks when PageSpeed is unavailable
    if results.get("score") is None:
        critical = sum(1 for i in results["issues"] if i["severity"] == "critical")
        warning = sum(1 for i in results["issues"] if i["severity"] == "warning")
        ok = sum(1 for i in results["issues"] if i["severity"] == "ok")
        total = critical + warning + ok
        if total:
            results["score"] = round((ok / total) * 100)

    return results
