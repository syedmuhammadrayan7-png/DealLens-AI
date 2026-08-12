from __future__ import annotations

import re

import httpx

from backend.utils.cache import TTLCache
from backend.utils.retry import PermanentExternalError, retry_external

GITHUB_RE = re.compile(r"^https?://(?:www\.)?github\.com/([\w.-]+)/([\w.-]+)/?$")


class GitHubService:
    def __init__(self, cache: TTLCache, token: str | None = None):
        self.cache, self.token = cache, token

    def inspect(self, url: str) -> dict:
        match = GITHUB_RE.match(url)
        if not match:
            raise PermanentExternalError("GitHub URL must identify a public owner/repository.")
        owner, repo = match.groups()
        return self.cache.get_or_set(f"github:{owner}/{repo}", lambda: self._fetch(owner, repo, self.token))

    @staticmethod
    def _fetch(owner: str, repo: str, token: str | None = None) -> dict:
        def request() -> dict:
            headers = {"Accept": "application/vnd.github+json", "User-Agent": "DealLensAI/0.1"}
            if token:
                headers["Authorization"] = f"Bearer {token}"
            response = httpx.get(f"https://api.github.com/repos/{owner}/{repo}", timeout=8.0, headers=headers)
            if response.status_code == 404:
                raise PermanentExternalError("Repository is unavailable or private.")
            if response.status_code in {401, 403, 429}:
                raise PermanentExternalError("GitHub repository evidence is temporarily unavailable or rate-limited.")
            response.raise_for_status()
            data = response.json()
            base = {key: data.get(key) for key in ("full_name", "description", "language", "stargazers_count", "forks_count", "open_issues_count", "updated_at", "pushed_at", "license", "default_branch")}
            commits = httpx.get(f"https://api.github.com/repos/{owner}/{repo}/commits?per_page=5", timeout=8.0, headers=headers)
            releases = httpx.get(f"https://api.github.com/repos/{owner}/{repo}/releases?per_page=5", timeout=8.0, headers=headers)
            contributors = httpx.get(f"https://api.github.com/repos/{owner}/{repo}/contributors?per_page=100", timeout=8.0, headers=headers)
            languages = httpx.get(f"https://api.github.com/repos/{owner}/{repo}/languages", timeout=8.0, headers=headers)
            base.update({
                "recent_commit_count": len(commits.json()) if commits.is_success and isinstance(commits.json(), list) else None,
                "release_count": len(releases.json()) if releases.is_success and isinstance(releases.json(), list) else None,
                "contributor_count": len(contributors.json()) if contributors.is_success and isinstance(contributors.json(), list) else None,
                "languages": languages.json() if languages.is_success and isinstance(languages.json(), dict) else {},
            })
            return base
        return retry_external(request, max_attempts=3)
