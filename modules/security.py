import ssl
import socket
import requests
from datetime import datetime
from urllib.parse import urlparse
from modules.http import SESSION


SECURITY_HEADERS = {
    "Strict-Transport-Security": {
        "severity": "critical",
        "desc": "HSTS not set — forces HTTPS and prevents downgrade attacks",
    },
    "Content-Security-Policy": {
        "severity": "critical",
        "desc": "CSP not set — no protection against XSS and injection attacks",
    },
    "X-Frame-Options": {
        "severity": "warning",
        "desc": "X-Frame-Options not set — site may be embeddable (clickjacking risk)",
    },
    "X-Content-Type-Options": {
        "severity": "warning",
        "desc": "X-Content-Type-Options not set — browsers may sniff MIME types",
    },
    "Referrer-Policy": {
        "severity": "info",
        "desc": "Referrer-Policy not set — full URL may leak in referer header",
    },
    "Permissions-Policy": {
        "severity": "info",
        "desc": "Permissions-Policy not set — no control over browser features",
    },
}


def analyze_security(url: str) -> dict:
    results = {"score": None, "issues": [], "details": {}}
    parsed = urlparse(url)

    # HTTPS check
    if parsed.scheme != "https":
        results["issues"].append({"severity": "critical", "msg": "Site is not using HTTPS — all data is transmitted in plaintext"})
    else:
        results["issues"].append({"severity": "ok", "msg": "Site uses HTTPS"})

    # Fetch with headers
    try:
        r = SESSION.get(url, timeout=15, allow_redirects=True)
        headers = {k.lower(): v for k, v in r.headers.items()}
        results["details"]["status_code"] = r.status_code
        results["details"]["final_url"] = r.url

        # HTTP → HTTPS redirect
        if parsed.scheme == "http":
            http_url = url
            try:
                rr = SESSION.get(http_url, timeout=10, allow_redirects=True)
                if rr.url.startswith("https://"):
                    results["issues"].append({"severity": "ok", "msg": "HTTP redirects to HTTPS"})
                else:
                    results["issues"].append({"severity": "critical", "msg": "HTTP does NOT redirect to HTTPS"})
            except Exception:
                pass

        # Security headers
        for header, meta in SECURITY_HEADERS.items():
            if header.lower() in headers:
                results["issues"].append({"severity": "ok", "msg": f"{header}: present"})
                results["details"][header] = headers[header.lower()]
            else:
                results["issues"].append({"severity": meta["severity"], "msg": f"Missing {header} — {meta['desc']}"})

        # Exposed server info
        server = headers.get("server", "")
        if server:
            results["issues"].append({"severity": "warning", "msg": f"Server header exposed: '{server}' — reveals technology stack"})
        x_powered = headers.get("x-powered-by", "")
        if x_powered:
            results["issues"].append({"severity": "warning", "msg": f"X-Powered-By header exposed: '{x_powered}' — reveals backend technology"})

        # Mixed content (basic check via CSP)
        csp = headers.get("content-security-policy", "")
        if "http://" in csp:
            results["issues"].append({"severity": "warning", "msg": "CSP contains http:// URLs — potential mixed content"})

        # Cookies
        for cookie in r.cookies:
            flags = []
            if not cookie.secure:
                flags.append("missing Secure flag")
            if "HttpOnly" not in cookie._rest:
                flags.append("missing HttpOnly flag")
            if flags:
                results["issues"].append({"severity": "warning", "msg": f"Cookie '{cookie.name}': {', '.join(flags)}"})

    except requests.exceptions.SSLError as e:
        results["issues"].append({"severity": "critical", "msg": f"SSL certificate error: {e}"})
        return results
    except Exception as e:
        results["issues"].append({"severity": "critical", "msg": f"Could not fetch site: {e}"})
        return results

    # SSL certificate details
    if parsed.scheme == "https":
        try:
            host = parsed.hostname
            port = parsed.port or 443
            ctx = ssl.create_default_context()
            with ctx.wrap_socket(socket.create_connection((host, port), timeout=10), server_hostname=host) as ssock:
                cert = ssock.getpeercert()
                not_after = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z")
                days_left = (not_after - datetime.utcnow()).days
                results["details"]["ssl_expires"] = not_after.strftime("%Y-%m-%d")
                results["details"]["ssl_days_left"] = days_left

                if days_left < 0:
                    results["issues"].append({"severity": "critical", "msg": f"SSL certificate has EXPIRED ({abs(days_left)} days ago)"})
                elif days_left < 14:
                    results["issues"].append({"severity": "critical", "msg": f"SSL certificate expires in {days_left} days — URGENT renewal needed"})
                elif days_left < 30:
                    results["issues"].append({"severity": "warning", "msg": f"SSL certificate expires in {days_left} days — renew soon"})
                else:
                    results["issues"].append({"severity": "ok", "msg": f"SSL certificate valid for {days_left} more days (expires {not_after.strftime('%Y-%m-%d')})"})

                # TLS version
                tls_version = ssock.version()
                results["details"]["tls_version"] = tls_version
                if tls_version in ("TLSv1", "TLSv1.1", "SSLv2", "SSLv3"):
                    results["issues"].append({"severity": "critical", "msg": f"Outdated TLS version: {tls_version} — upgrade to TLS 1.2+"})
                else:
                    results["issues"].append({"severity": "ok", "msg": f"TLS version: {tls_version}"})

        except ssl.CertificateError as e:
            results["issues"].append({"severity": "critical", "msg": f"SSL certificate invalid: {e}"})
        except Exception as e:
            results["issues"].append({"severity": "warning", "msg": f"Could not inspect SSL certificate: {e}"})

    # Compute a simple security score
    critical = sum(1 for i in results["issues"] if i["severity"] == "critical")
    warning = sum(1 for i in results["issues"] if i["severity"] == "warning")
    ok = sum(1 for i in results["issues"] if i["severity"] == "ok")
    total = critical + warning + ok
    if total:
        score = round((ok / total) * 100)
        results["score"] = score

    return results
