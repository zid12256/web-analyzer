import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from modules.http import SESSION


MAX_LINKS_TO_CHECK = 50


def check_link(url: str, base_url: str) -> dict:
    try:
        r = SESSION.head(url, timeout=8, allow_redirects=True)
        status = r.status_code
        if status == 405:
            r = SESSION.get(url, timeout=8, stream=True)
            status = r.status_code
        return {"url": url, "status": status, "ok": status < 400}
    except requests.exceptions.SSLError:
        return {"url": url, "status": "SSL Error", "ok": False}
    except requests.exceptions.ConnectionError:
        return {"url": url, "status": "Connection Error", "ok": False}
    except requests.exceptions.Timeout:
        return {"url": url, "status": "Timeout", "ok": False}
    except Exception as e:
        return {"url": url, "status": str(e)[:40], "ok": False}


def analyze_links(url: str) -> dict:
    results = {
        "issues": [],
        "details": {
            "total_links": 0,
            "broken": [],
            "redirects": [],
            "external": 0,
            "internal": 0,
        }
    }

    try:
        r = SESSION.get(url, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        results["issues"].append({"severity": "critical", "msg": f"Could not fetch page: {e}"})
        return results

    parsed_base = urlparse(url)
    base_domain = parsed_base.netloc

    # Collect all links
    all_links = set()
    for tag in soup.find_all("a", href=True):
        href = tag["href"].strip()
        if href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:") or href.startswith("javascript:"):
            continue
        full_url = urljoin(url, href)
        parsed = urlparse(full_url)
        if parsed.scheme in ("http", "https"):
            all_links.add(full_url)

    # Collect asset links (img, script, link)
    asset_links = set()
    for tag in soup.find_all(["img", "script", "link"]):
        src = tag.get("src") or tag.get("href") or ""
        if src and not src.startswith("data:"):
            full_url = urljoin(url, src)
            parsed = urlparse(full_url)
            if parsed.scheme in ("http", "https"):
                asset_links.add(full_url)

    # Count internal vs external
    internal = [l for l in all_links if urlparse(l).netloc == base_domain]
    external = [l for l in all_links if urlparse(l).netloc != base_domain]
    results["details"]["total_links"] = len(all_links)
    results["details"]["internal"] = len(internal)
    results["details"]["external"] = len(external)

    # Check links (limit to MAX_LINKS_TO_CHECK)
    links_to_check = list(all_links)[:MAX_LINKS_TO_CHECK]
    assets_to_check = list(asset_links)[:20]
    all_to_check = links_to_check + assets_to_check

    broken = []
    redirects = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(check_link, link, url): link for link in all_to_check}
        for future in as_completed(futures):
            result = future.result()
            if not result["ok"]:
                broken.append(result)
            elif isinstance(result["status"], int) and result["status"] in (301, 302, 307, 308):
                redirects.append(result)

    results["details"]["broken"] = broken
    results["details"]["redirects"] = redirects

    if broken:
        results["issues"].append({"severity": "critical", "msg": f"{len(broken)} broken link(s)/asset(s) found"})
        for b in broken[:5]:
            results["issues"].append({"severity": "critical", "msg": f"  Broken [{b['status']}]: {b['url'][:80]}"})
        if len(broken) > 5:
            results["issues"].append({"severity": "info", "msg": f"  ...and {len(broken)-5} more broken links"})
    else:
        results["issues"].append({"severity": "ok", "msg": f"No broken links found ({len(links_to_check)} checked)"})

    if redirects:
        results["issues"].append({"severity": "info", "msg": f"{len(redirects)} redirect(s) found (consider updating to final URLs)"})

    # Mixed content check
    http_assets = [a for a in asset_links if a.startswith("http://") and parsed_base.scheme == "https"]
    if http_assets:
        results["issues"].append({"severity": "critical", "msg": f"{len(http_assets)} mixed content asset(s): HTTP resources loaded on HTTPS page"})
        for a in http_assets[:3]:
            results["issues"].append({"severity": "critical", "msg": f"  Mixed content: {a[:80]}"})

    # External links count
    if external:
        results["issues"].append({"severity": "info", "msg": f"{len(external)} external link(s) found"})

    return results
