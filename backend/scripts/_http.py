"""Shared HTTPS helpers for the curation scripts.

Uses the certifi CA bundle explicitly. On macOS, the python.org installer ships without a system CA bundle, so
plain urllib fails with CERTIFICATE_VERIFY_FAILED until "Install Certificates.command" is run. Certificate
verification stays ON; only the trust store is made explicit.
"""
from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.request

try:
    import certifi

    _CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:  # pragma: no cover - certifi is in requirements.txt
    _CTX = ssl.create_default_context()

USER_AGENT = "cancerbiomap-curation/1.1 (academic project)"


def request(url: str, *, data: dict | None = None, as_json: bool = True, timeout: int = 90, retries: int = 3):
    """GET (or POST JSON when ``data`` is given) with a small retry/backoff for transient errors."""
    body = json.dumps(data).encode() if data is not None else None
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    if body is not None:
        headers["Content-Type"] = "application/json"
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=body, headers=headers, method="POST" if body else "GET")
            with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as resp:
                raw = resp.read()
            return json.loads(raw) if as_json else raw.decode()
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("unreachable")
