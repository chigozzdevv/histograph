import base64
import time
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote

import httpx
import jwt

from histograph.integrations.github.types import (
    CreatedDeployment,
    CreatedPullRequest,
    GitHubRepositoryFile,
)
from histograph.settings import Settings


class GitHubClient(Protocol):
    async def get_file(self, connection: dict[str, Any]) -> GitHubRepositoryFile: ...

    async def create_pull_request(
        self,
        connection: dict[str, Any],
        *,
        head_branch: str,
        content: str,
        title: str,
        body: str,
    ) -> CreatedPullRequest: ...


class GitHubDeploymentClient(GitHubClient, Protocol):
    async def create_deployment(
        self,
        connection: dict[str, Any],
        *,
        revision: str,
        environment: str,
        payload: dict[str, Any],
    ) -> CreatedDeployment: ...

    async def create_deployment_status(
        self,
        connection: dict[str, Any],
        *,
        deployment_id: int,
        state: str,
        environment: str,
        description: str,
        log_url: str | None = None,
    ) -> None: ...


class GitHubAppClient:
    def __init__(
        self,
        app_id: int,
        private_key: str,
        *,
        api_url: str = "https://api.github.com",
        api_version: str = "2026-03-10",
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._app_id = app_id
        self._private_key = private_key
        self._api_url = api_url.rstrip("/")
        self._api_version = api_version
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def get_file(self, connection: dict[str, Any]) -> GitHubRepositoryFile:
        return await self.get_repository_file(connection, str(connection["manifest_path"]))

    async def get_repository_file(
        self,
        connection: dict[str, Any],
        path: str,
        *,
        revision: str | None = None,
    ) -> GitHubRepositoryFile:
        token = await self._installation_token(int(connection["installation_id"]))
        owner, repository = _repository(connection)
        resolved_revision = revision
        if resolved_revision is None:
            branch = str(connection["branch"])
            ref_payload = await self._request(
                "GET",
                f"/repos/{owner}/{repository}/git/ref/heads/{quote(branch, safe='/')}",
                token,
            )
            if not isinstance(ref_payload, dict):
                raise RuntimeError("GitHub returned an invalid repository reference response")
            resolved_revision = (ref_payload.get("object") or {}).get("sha")
            if not isinstance(resolved_revision, str) or not resolved_revision:
                raise RuntimeError("GitHub repository reference is missing its revision")
        repository_path = quote(path, safe="/")
        file_payload = await self._request(
            "GET",
            f"/repos/{owner}/{repository}/contents/{repository_path}",
            token,
            params={"ref": resolved_revision},
        )
        if not isinstance(file_payload, dict):
            raise RuntimeError("GitHub returned an invalid repository file response")
        encoded = file_payload.get("content")
        blob_sha = file_payload.get("sha")
        if not isinstance(encoded, str) or not encoded:
            raise RuntimeError("GitHub repository file response is missing content")
        if not isinstance(blob_sha, str) or not blob_sha:
            raise RuntimeError("GitHub repository file response is missing its blob SHA")
        try:
            content = base64.b64decode(encoded).decode()
        except (ValueError, UnicodeDecodeError) as error:
            raise RuntimeError("GitHub deployment manifest is not valid UTF-8") from error
        return GitHubRepositoryFile(
            content=content,
            blob_sha=blob_sha,
            revision=resolved_revision,
        )

    async def create_pull_request(
        self,
        connection: dict[str, Any],
        *,
        head_branch: str,
        content: str,
        title: str,
        body: str,
    ) -> CreatedPullRequest:
        token = await self._installation_token(int(connection["installation_id"]))
        owner, repository = _repository(connection)
        base_branch = str(connection["branch"])
        existing = await self._existing_pull_request(
            token, owner, repository, head_branch, base_branch
        )
        if existing is not None:
            return existing

        base_ref = await self._request(
            "GET",
            f"/repos/{owner}/{repository}/git/ref/heads/{quote(base_branch, safe='/')}",
            token,
        )
        if not isinstance(base_ref, dict):
            raise RuntimeError("GitHub returned an invalid base branch response")
        base_sha = (base_ref.get("object") or {}).get("sha")
        if not isinstance(base_sha, str) or not base_sha:
            raise RuntimeError("GitHub base branch response has no revision")
        await self._ensure_branch(token, owner, repository, head_branch, base_sha)

        path = quote(str(connection["manifest_path"]), safe="/")
        branch_file = await self._request(
            "GET",
            f"/repos/{owner}/{repository}/contents/{path}",
            token,
            params={"ref": head_branch},
        )
        if not isinstance(branch_file, dict) or not isinstance(branch_file.get("sha"), str):
            raise RuntimeError("GitHub rollback branch has no deployment manifest")
        current_content = branch_file.get("content")
        decoded = ""
        if isinstance(current_content, str):
            decoded = base64.b64decode(current_content).decode()
        if decoded != content:
            await self._request(
                "PUT",
                f"/repos/{owner}/{repository}/contents/{path}",
                token,
                json={
                    "message": title,
                    "content": base64.b64encode(content.encode()).decode(),
                    "sha": branch_file["sha"],
                    "branch": head_branch,
                },
            )

        payload = await self._request(
            "POST",
            f"/repos/{owner}/{repository}/pulls",
            token,
            json={
                "title": title,
                "head": head_branch,
                "base": base_branch,
                "body": body,
                "draft": False,
            },
        )
        return _pull_request(payload, head_branch)

    async def create_deployment(
        self,
        connection: dict[str, Any],
        *,
        revision: str,
        environment: str,
        payload: dict[str, Any],
    ) -> CreatedDeployment:
        token = await self._installation_token(int(connection["installation_id"]))
        owner, repository = _repository(connection)
        response = await self._request(
            "POST",
            f"/repos/{owner}/{repository}/deployments",
            token,
            json={
                "ref": revision,
                "environment": environment,
                "auto_merge": False,
                "required_contexts": [],
                "payload": payload,
                "description": "Apply Histograph model deployment manifest",
                "production_environment": environment == "production",
            },
        )
        if not isinstance(response, dict):
            raise RuntimeError("GitHub returned an invalid deployment response")
        deployment_id = response.get("id")
        resolved_revision = response.get("sha")
        if not isinstance(deployment_id, int) or not isinstance(resolved_revision, str):
            raise RuntimeError("GitHub deployment response has no identifier or revision")
        return CreatedDeployment(id=deployment_id, revision=resolved_revision)

    async def create_deployment_status(
        self,
        connection: dict[str, Any],
        *,
        deployment_id: int,
        state: str,
        environment: str,
        description: str,
        log_url: str | None = None,
    ) -> None:
        token = await self._installation_token(int(connection["installation_id"]))
        owner, repository = _repository(connection)
        body: dict[str, Any] = {
            "state": state,
            "environment": environment,
            "description": description[:140],
            "auto_inactive": state == "success",
        }
        if log_url is not None:
            body["log_url"] = log_url
        await self._request(
            "POST",
            f"/repos/{owner}/{repository}/deployments/{deployment_id}/statuses",
            token,
            json=body,
        )

    async def _installation_token(self, installation_id: int) -> str:
        now = int(time.time())
        app_jwt = jwt.encode(
            {"iat": now - 60, "exp": now + 540, "iss": str(self._app_id)},
            self._private_key,
            algorithm="RS256",
        )
        payload = await self._request(
            "POST",
            f"/app/installations/{installation_id}/access_tokens",
            app_jwt,
            app_auth=True,
        )
        token = payload.get("token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token:
            raise RuntimeError("GitHub App installation did not return an access token")
        return token

    async def _existing_pull_request(
        self,
        token: str,
        owner: str,
        repository: str,
        head_branch: str,
        base_branch: str,
    ) -> CreatedPullRequest | None:
        payload = await self._request(
            "GET",
            f"/repos/{owner}/{repository}/pulls",
            token,
            params={"head": f"{owner}:{head_branch}", "base": base_branch, "state": "all"},
        )
        if not isinstance(payload, list) or not payload:
            return None
        return _pull_request(payload[0], head_branch)

    async def _ensure_branch(
        self,
        token: str,
        owner: str,
        repository: str,
        head_branch: str,
        base_sha: str,
    ) -> None:
        try:
            await self._request(
                "POST",
                f"/repos/{owner}/{repository}/git/refs",
                token,
                json={"ref": f"refs/heads/{head_branch}", "sha": base_sha},
            )
        except httpx.HTTPStatusError as error:
            if error.response.status_code != 422:
                raise

    async def _request(
        self,
        method: str,
        path: str,
        token: str,
        *,
        app_auth: bool = False,
        params: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
    ) -> Any:
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": self._api_version,
        }
        async with httpx.AsyncClient(
            base_url=self._api_url,
            timeout=self._timeout_seconds,
            headers=headers,
            transport=self._transport,
        ) as client:
            response = await client.request(method, path, params=params, json=json)
        response.raise_for_status()
        if response.status_code == 204:
            return None
        return response.json()


def build_github_client(settings: Settings) -> GitHubAppClient | None:
    if settings.github_app_id is None:
        return None
    private_key = settings.github_app_private_key
    if private_key is None and settings.github_app_private_key_path is not None:
        private_key = Path(settings.github_app_private_key_path).read_text()
    if private_key is None:
        return None
    return GitHubAppClient(
        settings.github_app_id,
        private_key.replace("\\n", "\n"),
        api_url=settings.github_api_url,
        api_version=settings.github_api_version,
    )


def _repository(connection: dict[str, Any]) -> tuple[str, str]:
    return str(connection["repository_owner"]), str(connection["repository_name"])


def _pull_request(payload: Any, head_branch: str) -> CreatedPullRequest:
    if not isinstance(payload, dict):
        raise RuntimeError("GitHub returned an invalid pull request response")
    number, url = payload.get("number"), payload.get("html_url")
    if not isinstance(number, int) or not isinstance(url, str) or not url:
        raise RuntimeError("GitHub pull request response is missing its number or URL")
    return CreatedPullRequest(number=number, url=url, head_branch=head_branch)
