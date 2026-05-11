"""Shared HTTP session with macOS SSL fix and sensible defaults."""
import ssl
import requests
import certifi


def get_session() -> requests.Session:
    session = requests.Session()
    session.verify = certifi.where()
    session.headers.update({"User-Agent": "WebAnalyzer/1.0"})
    return session


# Module-level default session
SESSION = get_session()
