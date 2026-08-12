"""Low-friction public website research; it remains optional and evidence-labelled."""
from __future__ import annotations

import re
from html import unescape
from urllib.parse import urlparse

import httpx

from backend.utils.cache import TTLCache
from backend.utils.retry import ExternalServiceError, PermanentExternalError, retry_external


class WebsiteResearchService:
    def __init__(self, cache: TTLCache):
        self.cache = cache

    def inspect(self, url: str | None) -> dict[str, str | None]:
        if not url:
            return {"status": "unavailable", "reason": "No website was supplied."}
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise PermanentExternalError("Website must be an absolute HTTP(S) URL.")
        return self.cache.get_or_set(f"website:{url}", lambda: self._fetch(url))

    @staticmethod
    def _fetch(url: str) -> dict[str, str | None]:
        def request() -> dict[str, str | None]:
            response = httpx.get(url, timeout=8.0, follow_redirects=True, headers={"User-Agent": "DealLensAI/0.1 research"})
            if response.status_code in {401, 403, 404}:
                raise PermanentExternalError(f"Public website is unavailable (HTTP {response.status_code}).")
            response.raise_for_status()
            body = response.text[:80_000]
            title = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
            description = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', body, re.I | re.S)
            text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))[:3_000]
            return {"status": "supported", "url": str(response.url), "title": unescape(title.group(1).strip()) if title else None, "description": unescape(description.group(1).strip()) if description else None, "excerpt": unescape(text).strip()}
        try:
            return retry_external(request, max_attempts=3)
        except (PermanentExternalError, ExternalServiceError) as exc:
            return {"status": "unavailable", "reason": str(exc)}
