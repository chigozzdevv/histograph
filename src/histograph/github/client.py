import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import jwt


class GitHubApiError(RuntimeError):
    pass


class GitHubAppClient:
    def __init__(
        self,
        *,
        app_id: str,
        private_key: str,
        api_url: str = "https://api.github.com",
        api_version: str = "2026-03-10",
        http_client: httpx.AsyncClient | None = None,
    ):
        self._app_id = app_id
        self._private_key = private_key.replace("\\n", "\n")
        self._api_url = api_url.rstrip("/")
        self._api_version = api_version
        self._http = http_client or httpx.AsyncClient(timeout=30, follow_redirects=True)
        self._owns_http_client = http_client is None
        self._tokens: dict[int, tuple[str, datetime]] = {}
        self._token_lock = asyncio.Lock()

    async def close(self) -> None:
        if self._owns_http_client:
            await self._http.aclose()

    async def get_installation(self, installation_id: int) -> dict[str, Any]:
        return await self._request_app("GET", f"/app/installations/{installation_id}")

    async def list_repositories(self, installation_id: int) -> tuple[dict[str, Any], ...]:
        token = await self._installation_token(installation_id)
        repositories: list[dict[str, Any]] = []
        page = 1
        while True:
            payload = await self._request_installation(
                token,
                "GET",
                "/installation/repositories",
                params={"per_page": 100, "page": page},
            )
            items = payload.get("repositories", [])
            repositories.extend(item for item in items if isinstance(item, dict))
            if len(items) < 100:
                break
            page += 1
        return tuple(repositories)

    async def list_pull_request_files(
        self,
        installation_id: int,
        owner: str,
        repository: str,
        pull_number: int,
    ) -> tuple[str, ...]:
        token = await self._installation_token(installation_id)
        filenames: list[str] = []
        page = 1
        while True:
            payload = await self._request_installation(
                token,
                "GET",
                f"/repos/{owner}/{repository}/pulls/{pull_number}/files",
                params={"per_page": 100, "page": page},
            )
            if not isinstance(payload, list):
                raise GitHubApiError("GitHub returned an invalid pull-request files response")
            filenames.extend(
                item["filename"]
                for item in payload
                if isinstance(item, dict) and isinstance(item.get("filename"), str)
            )
            if len(payload) < 100:
                break
            page += 1
        return tuple(dict.fromkeys(filenames))

    async def list_compare_files(
        self,
        installation_id: int,
        owner: str,
        repository: str,
        base_sha: str,
        head_sha: str,
    ) -> tuple[str, ...]:
        token = await self._installation_token(installation_id)
        payload = await self._request_installation(
            token,
            "GET",
            f"/repos/{owner}/{repository}/compare/{base_sha}...{head_sha}",
            params={"per_page": 100},
        )
        files = payload.get("files", [])
        if not isinstance(files, list):
            raise GitHubApiError("GitHub returned an invalid commit comparison response")
        return tuple(
            dict.fromkeys(
                item["filename"]
                for item in files
                if isinstance(item, dict) and isinstance(item.get("filename"), str)
            )
        )

    async def create_check_run(
        self,
        *,
        installation_id: int,
        owner: str,
        repository: str,
        head_sha: str,
        external_id: str,
        details_url: str | None,
    ) -> int:
        token = await self._installation_token(installation_id)
        payload = await self._request_installation(
            token,
            "POST",
            f"/repos/{owner}/{repository}/check-runs",
            json={
                "name": "Histograph context assurance",
                "head_sha": head_sha,
                "status": "queued",
                "external_id": external_id,
                "details_url": details_url,
                "output": {
                    "title": "Histograph is planning affected agent tests",
                    "summary": (
                        "DataHub lineage will determine which protected questions are at risk."
                    ),
                },
            },
        )
        check_id = payload.get("id")
        if not isinstance(check_id, int):
            raise GitHubApiError("GitHub did not return a check-run identifier")
        return check_id

    async def find_check_run(
        self,
        *,
        installation_id: int,
        owner: str,
        repository: str,
        head_sha: str,
        external_id: str,
    ) -> int | None:
        token = await self._installation_token(installation_id)
        payload = await self._request_installation(
            token,
            "GET",
            f"/repos/{owner}/{repository}/commits/{head_sha}/check-runs",
            params={"check_name": "Histograph context assurance", "per_page": 100},
        )
        check_runs = payload.get("check_runs", [])
        if not isinstance(check_runs, list):
            raise GitHubApiError("GitHub returned an invalid check-runs response")
        for check_run in check_runs:
            if not isinstance(check_run, dict):
                continue
            if str(check_run.get("external_id", "")) != external_id:
                continue
            check_id = check_run.get("id")
            if isinstance(check_id, int):
                return check_id
        return None

    async def ensure_check_run(
        self,
        *,
        installation_id: int,
        owner: str,
        repository: str,
        head_sha: str,
        external_id: str,
        details_url: str | None,
    ) -> int:
        existing = await self.find_check_run(
            installation_id=installation_id,
            owner=owner,
            repository=repository,
            head_sha=head_sha,
            external_id=external_id,
        )
        if existing is not None:
            return existing
        return await self.create_check_run(
            installation_id=installation_id,
            owner=owner,
            repository=repository,
            head_sha=head_sha,
            external_id=external_id,
            details_url=details_url,
        )

    async def update_check_run(
        self,
        *,
        installation_id: int,
        owner: str,
        repository: str,
        check_run_id: int,
        status: str,
        title: str,
        summary: str,
        conclusion: str | None = None,
    ) -> None:
        token = await self._installation_token(installation_id)
        body: dict[str, Any] = {
            "status": status,
            "output": {"title": title, "summary": summary},
        }
        if conclusion:
            body["conclusion"] = conclusion
            body["completed_at"] = datetime.now(UTC).isoformat()
        await self._request_installation(
            token,
            "PATCH",
            f"/repos/{owner}/{repository}/check-runs/{check_run_id}",
            json=body,
        )

    def _app_jwt(self) -> str:
        now = datetime.now(UTC)
        return jwt.encode(
            {
                "iat": int((now - timedelta(seconds=60)).timestamp()),
                "exp": int((now + timedelta(minutes=9)).timestamp()),
                "iss": self._app_id,
            },
            self._private_key,
            algorithm="RS256",
        )

    async def _installation_token(self, installation_id: int) -> str:
        cached = self._tokens.get(installation_id)
        now = datetime.now(UTC)
        if cached and cached[1] > now + timedelta(minutes=2):
            return cached[0]
        async with self._token_lock:
            cached = self._tokens.get(installation_id)
            if cached and cached[1] > now + timedelta(minutes=2):
                return cached[0]
            payload = await self._request_app(
                "POST", f"/app/installations/{installation_id}/access_tokens"
            )
            token = payload.get("token")
            expires_at = payload.get("expires_at")
            if not isinstance(token, str) or not isinstance(expires_at, str):
                raise GitHubApiError("GitHub did not return a valid installation token")
            try:
                expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            except ValueError as error:
                raise GitHubApiError("GitHub returned an invalid token expiration") from error
            self._tokens[installation_id] = (token, expires)
            return token

    async def _request_app(self, method: str, path: str, **kwargs: Any) -> Any:
        return await self._request(method, path, self._app_jwt(), **kwargs)

    async def _request_installation(self, token: str, method: str, path: str, **kwargs: Any) -> Any:
        return await self._request(method, path, token, **kwargs)

    async def _request(self, method: str, path: str, token: str, **kwargs: Any) -> Any:
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": self._api_version,
        }
        response = await self._http.request(
            method, f"{self._api_url}{path}", headers=headers, **kwargs
        )
        if response.is_error:
            request_id = response.headers.get("x-github-request-id", "unknown")
            raise GitHubApiError(
                f"GitHub API returned {response.status_code} (request {request_id})"
            )
        if response.status_code == 204:
            return {}
        return response.json()
