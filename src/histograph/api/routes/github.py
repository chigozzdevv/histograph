from datetime import UTC, datetime
from fnmatch import fnmatch
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from histograph.api.database.models import (
    GitHubInstallationRecord,
    RepositoryConnectionRecord,
    RunRecord,
    WebhookReceiptRecord,
)
from histograph.api.database.models.common import ReceiptStatus, Role, RunStatus, TriggerType
from histograph.api.database.session import get_session
from histograph.api.schemas import (
    ConnectGitHubInstallationRequest,
    ConnectRepositoryRequest,
    GitHubInstallationResponse,
    RepositoryConnectionResponse,
)
from histograph.api.security import Actor, get_actor
from histograph.api.security.authorization import authorize_organization, authorize_project
from histograph.api.services.audit import add_audit_event
from histograph.api.services.orchestration import Orchestrator
from histograph.api.services.requests import request_id, source_ip
from histograph.github import GitHubAppClient, verify_webhook_signature
from histograph.security import stable_fingerprint

router = APIRouter(tags=["github"])


@router.get(
    "/organizations/{organization_id}/github-installations",
    response_model=tuple[GitHubInstallationResponse, ...],
)
async def list_installations(
    organization_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> tuple[GitHubInstallationRecord, ...]:
    await authorize_organization(session, actor, organization_id)
    records = await session.scalars(
        select(GitHubInstallationRecord)
        .where(
            GitHubInstallationRecord.organization_id == organization_id,
            GitHubInstallationRecord.deleted_at.is_(None),
        )
        .order_by(GitHubInstallationRecord.account_login)
    )
    return tuple(records)


@router.post(
    "/organizations/{organization_id}/github-installations",
    response_model=GitHubInstallationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def connect_installation(
    organization_id: str,
    body: ConnectGitHubInstallationRequest,
    request: Request,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GitHubInstallationRecord:
    await authorize_organization(session, actor, organization_id, {Role.OWNER, Role.ADMIN})
    github = _github_client(request)
    payload = await github.get_installation(body.installation_id)
    account = payload.get("account") or {}
    permissions = payload.get("permissions") or {}
    _validate_installation_permissions(permissions)
    existing = await session.scalar(
        select(GitHubInstallationRecord).where(
            GitHubInstallationRecord.installation_id == body.installation_id
        )
    )
    if existing and existing.organization_id != organization_id:
        raise HTTPException(
            status_code=409, detail="GitHub installation belongs to another organization"
        )
    record = existing or GitHubInstallationRecord(
        organization_id=organization_id,
        installation_id=body.installation_id,
        account_login="",
        account_type="unknown",
        repository_selection="selected",
        permissions_json={},
    )
    record.account_login = str(account.get("login", ""))
    record.account_type = str(account.get("type", "unknown"))
    record.repository_selection = str(payload.get("repository_selection", "selected"))
    record.permissions_json = permissions
    record.suspended_at = None
    record.deleted_at = None
    if not record.account_login:
        raise HTTPException(status_code=502, detail="GitHub installation account is unavailable")
    session.add(record)
    try:
        await session.flush()
        add_audit_event(
            session,
            actor=actor,
            organization_id=organization_id,
            action="github_installation.connected",
            target_type="github_installation",
            target_id=record.id,
            request_id=request_id(request),
            source_ip=source_ip(request),
            after={
                "installation_id": record.installation_id,
                "account_login": record.account_login,
                "permissions": record.permissions_json,
            },
        )
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="GitHub installation is already connected"
        ) from error
    await session.refresh(record)
    return record


@router.get(
    "/projects/{project_id}/repositories",
    response_model=tuple[RepositoryConnectionResponse, ...],
)
async def list_repositories(
    project_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> tuple[RepositoryConnectionRecord, ...]:
    await authorize_project(session, actor, project_id)
    records = await session.scalars(
        select(RepositoryConnectionRecord)
        .where(
            RepositoryConnectionRecord.project_id == project_id,
            RepositoryConnectionRecord.deleted_at.is_(None),
        )
        .order_by(RepositoryConnectionRecord.full_name)
    )
    return tuple(records)


@router.post(
    "/projects/{project_id}/repositories",
    response_model=RepositoryConnectionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def connect_repository(
    project_id: str,
    body: ConnectRepositoryRequest,
    request: Request,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RepositoryConnectionRecord:
    project = await authorize_project(session, actor, project_id, {Role.OWNER, Role.ADMIN})
    installation = await session.scalar(
        select(GitHubInstallationRecord).where(
            GitHubInstallationRecord.id == body.github_installation_id,
            GitHubInstallationRecord.organization_id == project.organization_id,
            GitHubInstallationRecord.deleted_at.is_(None),
        )
    )
    if installation is None:
        raise HTTPException(status_code=404, detail="GitHub installation not found")
    if installation.suspended_at is not None:
        raise HTTPException(status_code=409, detail="GitHub installation is suspended")
    repositories = await _github_client(request).list_repositories(installation.installation_id)
    repository = next((item for item in repositories if item.get("id") == body.repository_id), None)
    if repository is None:
        raise HTTPException(
            status_code=404, detail="Repository is not available to the installation"
        )
    owner = repository.get("owner") or {}
    protected_branches = list(body.protected_branches) or [
        str(repository.get("default_branch", "main"))
    ]
    configuration = {
        "asset_mappings": [mapping.model_dump(mode="json") for mapping in body.asset_mappings],
        "run_all_when_unmapped": body.run_all_when_unmapped,
        "protected_branches": protected_branches,
        "run_draft_pull_requests": body.run_draft_pull_requests,
    }
    record = await session.scalar(
        select(RepositoryConnectionRecord).where(
            RepositoryConnectionRecord.project_id == project_id,
            RepositoryConnectionRecord.repository_id == repository["id"],
        )
    )
    record = record or RepositoryConnectionRecord(
        organization_id=project.organization_id,
        project_id=project_id,
        github_installation_id=installation.id,
        repository_id=repository["id"],
        owner="",
        name="",
        full_name="",
        default_branch="main",
        configuration_json={},
        active=True,
    )
    record.github_installation_id = installation.id
    record.owner = str(owner.get("login", ""))
    record.name = str(repository.get("name", ""))
    record.full_name = str(repository.get("full_name", ""))
    record.default_branch = str(repository.get("default_branch", "main"))
    record.configuration_json = configuration
    record.active = True
    record.deleted_at = None
    if not record.owner or not record.name:
        raise HTTPException(status_code=502, detail="GitHub repository metadata is incomplete")
    session.add(record)
    try:
        await session.flush()
        add_audit_event(
            session,
            actor=actor,
            organization_id=project.organization_id,
            project_id=project_id,
            action="repository.connected",
            target_type="repository_connection",
            target_id=record.id,
            request_id=request_id(request),
            source_ip=source_ip(request),
            after={"repository": record.full_name, "configuration": configuration},
        )
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Repository is already connected") from error
    await session.refresh(record)
    return record


@router.post("/webhooks/github", status_code=status.HTTP_202_ACCEPTED)
async def github_webhook(request: Request) -> dict[str, str]:
    settings = request.app.state.settings
    if not settings.github_webhook_secret:
        raise HTTPException(status_code=503, detail="GitHub webhooks are not configured")
    raw_payload = await request.body()
    if not verify_webhook_signature(
        raw_payload,
        request.headers.get("x-hub-signature-256"),
        settings.github_webhook_secret.get_secret_value(),
    ):
        raise HTTPException(status_code=401, detail="Invalid GitHub webhook signature")
    delivery_id = request.headers.get("x-github-delivery")
    event_type = request.headers.get("x-github-event")
    if not delivery_id or not event_type:
        raise HTTPException(status_code=400, detail="GitHub delivery headers are required")
    payload = await request.json()
    async with request.app.state.session_factory() as session:
        existing = await session.scalar(
            select(WebhookReceiptRecord).where(
                WebhookReceiptRecord.source == "github",
                WebhookReceiptRecord.delivery_id == delivery_id,
            )
        )
        if existing:
            if existing.run_id and existing.status in {
                ReceiptStatus.PROCESSING,
                ReceiptStatus.FAILED,
            }:
                return await _resume_github_run(session, request, existing)
            return {"status": existing.status.value, "receipt_id": existing.id}
        if event_type == "installation":
            return await _handle_installation_event(session, payload, delivery_id)
        if event_type == "installation_repositories":
            return await _handle_installation_repositories_event(session, payload, delivery_id)
        if event_type == "repository":
            return await _handle_repository_event(session, payload, delivery_id)
        if event_type not in {"pull_request", "push"}:
            receipt = WebhookReceiptRecord(
                source="github",
                delivery_id=delivery_id,
                event_type=event_type,
                action=payload.get("action"),
                signature_valid=True,
                payload_json=payload,
                status=ReceiptStatus.IGNORED,
            )
            session.add(receipt)
            await session.commit()
            return {"status": "ignored", "receipt_id": receipt.id}
        return await _queue_github_run(session, request, payload, delivery_id, event_type)


async def _handle_installation_event(
    session: AsyncSession, payload: dict[str, Any], delivery_id: str
) -> dict[str, str]:
    installation_payload = payload.get("installation") or {}
    installation_id = installation_payload.get("id")
    record = await session.scalar(
        select(GitHubInstallationRecord).where(
            GitHubInstallationRecord.installation_id == installation_id
        )
    )
    action = payload.get("action")
    receipt = WebhookReceiptRecord(
        organization_id=record.organization_id if record else None,
        source="github",
        delivery_id=delivery_id,
        event_type="installation",
        action=action,
        signature_valid=True,
        payload_json=payload,
        status=ReceiptStatus.PROCESSED if record else ReceiptStatus.IGNORED,
    )
    if record and action == "suspend":
        suspended_at = installation_payload.get("suspended_at")
        record.suspended_at = (
            datetime.fromisoformat(suspended_at.replace("Z", "+00:00"))
            if isinstance(suspended_at, str)
            else datetime.now(UTC)
        )
    if record and action == "unsuspend":
        record.suspended_at = None
    if record and action == "new_permissions_accepted":
        permissions = installation_payload.get("permissions") or {}
        _validate_installation_permissions(permissions)
        record.permissions_json = permissions
    if record and action == "deleted":
        record.deleted_at = datetime.now(UTC)
        repositories = await session.scalars(
            select(RepositoryConnectionRecord).where(
                RepositoryConnectionRecord.github_installation_id == record.id
            )
        )
        for repository in repositories:
            repository.active = False
    session.add(receipt)
    await session.commit()
    return {"status": receipt.status.value, "receipt_id": receipt.id}


async def _handle_installation_repositories_event(
    session: AsyncSession,
    payload: dict[str, Any],
    delivery_id: str,
) -> dict[str, str]:
    installation_id = (payload.get("installation") or {}).get("id")
    installation = await session.scalar(
        select(GitHubInstallationRecord).where(
            GitHubInstallationRecord.installation_id == installation_id
        )
    )
    receipt = WebhookReceiptRecord(
        organization_id=installation.organization_id if installation else None,
        source="github",
        delivery_id=delivery_id,
        event_type="installation_repositories",
        action=payload.get("action"),
        signature_valid=True,
        payload_json=payload,
        status=ReceiptStatus.PROCESSED if installation else ReceiptStatus.IGNORED,
    )
    if installation:
        removed_ids = {
            item.get("id")
            for item in payload.get("repositories_removed", [])
            if isinstance(item, dict) and isinstance(item.get("id"), int)
        }
        if removed_ids:
            repositories = await session.scalars(
                select(RepositoryConnectionRecord).where(
                    RepositoryConnectionRecord.github_installation_id == installation.id,
                    RepositoryConnectionRecord.repository_id.in_(removed_ids),
                )
            )
            for repository in repositories:
                repository.active = False
    session.add(receipt)
    await session.commit()
    return {"status": receipt.status.value, "receipt_id": receipt.id}


async def _handle_repository_event(
    session: AsyncSession,
    payload: dict[str, Any],
    delivery_id: str,
) -> dict[str, str]:
    repository_payload = payload.get("repository") or {}
    installation_id = (payload.get("installation") or {}).get("id")
    installation = await session.scalar(
        select(GitHubInstallationRecord).where(
            GitHubInstallationRecord.installation_id == installation_id
        )
    )
    repositories = ()
    if installation and isinstance(repository_payload.get("id"), int):
        repositories = tuple(
            await session.scalars(
                select(RepositoryConnectionRecord).where(
                    RepositoryConnectionRecord.github_installation_id == installation.id,
                    RepositoryConnectionRecord.repository_id == repository_payload["id"],
                )
            )
        )
    receipt = WebhookReceiptRecord(
        organization_id=installation.organization_id if installation else None,
        project_id=repositories[0].project_id if len(repositories) == 1 else None,
        source="github",
        delivery_id=delivery_id,
        event_type="repository",
        action=payload.get("action"),
        signature_valid=True,
        payload_json=payload,
        status=ReceiptStatus.PROCESSED if repositories else ReceiptStatus.IGNORED,
    )
    owner = repository_payload.get("owner") or {}
    for repository in repositories:
        repository.owner = str(owner.get("login", repository.owner))
        repository.name = str(repository_payload.get("name", repository.name))
        repository.full_name = str(repository_payload.get("full_name", repository.full_name))
        repository.default_branch = str(
            repository_payload.get("default_branch", repository.default_branch)
        )
        if payload.get("action") in {"archived", "deleted", "transferred"}:
            repository.active = False
        elif payload.get("action") == "unarchived":
            repository.active = True
    session.add(receipt)
    await session.commit()
    return {"status": receipt.status.value, "receipt_id": receipt.id}


async def _queue_github_run(
    session: AsyncSession,
    request: Request,
    payload: dict[str, Any],
    delivery_id: str,
    event_type: str,
) -> dict[str, str]:
    repository_payload = payload.get("repository") or {}
    repository = await session.scalar(
        select(RepositoryConnectionRecord).where(
            RepositoryConnectionRecord.repository_id == repository_payload.get("id"),
            RepositoryConnectionRecord.active.is_(True),
            RepositoryConnectionRecord.deleted_at.is_(None),
        )
    )
    if repository is None:
        receipt = WebhookReceiptRecord(
            source="github",
            delivery_id=delivery_id,
            event_type=event_type,
            action=payload.get("action"),
            signature_valid=True,
            payload_json=payload,
            status=ReceiptStatus.IGNORED,
        )
        session.add(receipt)
        await session.commit()
        return {"status": "ignored", "receipt_id": receipt.id}
    installation = await session.get(GitHubInstallationRecord, repository.github_installation_id)
    if installation is None or installation.suspended_at is not None:
        raise HTTPException(status_code=409, detail="GitHub installation is unavailable")
    payload_installation = payload.get("installation") or {}
    if payload_installation.get("id") != installation.installation_id:
        raise HTTPException(status_code=403, detail="GitHub installation does not match repository")
    github = _github_client(request)
    trigger_type: TriggerType
    trigger_reference: str
    head_sha: str
    changed_files: tuple[str, ...]
    if event_type == "pull_request":
        if payload.get("action") not in {"opened", "reopened", "synchronize", "ready_for_review"}:
            return await _ignored_receipt(session, repository, payload, delivery_id, event_type)
        pull_request = payload.get("pull_request") or {}
        protected_branches = repository.configuration_json.get(
            "protected_branches", [repository.default_branch]
        )
        base_branch = str((pull_request.get("base") or {}).get("ref", ""))
        if base_branch not in protected_branches:
            return await _ignored_receipt(session, repository, payload, delivery_id, event_type)
        if pull_request.get("draft") and not repository.configuration_json.get(
            "run_draft_pull_requests", False
        ):
            return await _ignored_receipt(session, repository, payload, delivery_id, event_type)
        pull_number = int(payload.get("number"))
        head_sha = str((pull_request.get("head") or {}).get("sha", ""))
        trigger_type = TriggerType.GITHUB_PULL_REQUEST
        trigger_reference = f"{repository.repository_id}:pull:{pull_number}"
        changed_files = await github.list_pull_request_files(
            installation.installation_id,
            repository.owner,
            repository.name,
            pull_number,
        )
    else:
        branch = str(payload.get("ref", "")).removeprefix("refs/heads/")
        protected_branches = repository.configuration_json.get(
            "protected_branches", [repository.default_branch]
        )
        if branch not in protected_branches or payload.get("deleted"):
            return await _ignored_receipt(session, repository, payload, delivery_id, event_type)
        head_sha = str(payload.get("after", ""))
        trigger_type = TriggerType.GITHUB_PUSH
        trigger_reference = f"{repository.repository_id}:push:{payload.get('ref', '')}"
        before_sha = str(payload.get("before", ""))
        if before_sha and set(before_sha) != {"0"}:
            changed_files = await github.list_compare_files(
                installation.installation_id,
                repository.owner,
                repository.name,
                before_sha,
                head_sha,
            )
        else:
            changed_files = _push_changed_files(payload)
    if not head_sha:
        raise HTTPException(status_code=422, detail="GitHub payload does not contain a head SHA")
    asset_urns = _mapped_assets(repository.configuration_json, changed_files)
    run_all = not asset_urns and bool(
        repository.configuration_json.get("run_all_when_unmapped", True)
    )
    selection = {
        "suite_ids": [],
        "test_ids": [],
        "asset_urns": list(asset_urns),
        "all_active": run_all,
        "github": {
            "repository_connection_id": repository.id,
            "installation_id": installation.installation_id,
            "owner": repository.owner,
            "repository": repository.name,
            "head_sha": head_sha,
            "changed_files": list(changed_files),
        },
    }
    receipt = WebhookReceiptRecord(
        organization_id=repository.organization_id,
        project_id=repository.project_id,
        source="github",
        delivery_id=delivery_id,
        event_type=event_type,
        action=payload.get("action"),
        signature_valid=True,
        payload_json=payload,
        status=ReceiptStatus.PROCESSING,
    )
    run = RunRecord(
        organization_id=repository.organization_id,
        project_id=repository.project_id,
        trigger_type=trigger_type,
        trigger_reference=trigger_reference,
        idempotency_key=f"github:{delivery_id}",
        requested_by=f"github:{installation.installation_id}",
        status=RunStatus.QUEUED,
        configuration_fingerprint=stable_fingerprint(
            {"repository": repository.id, "head_sha": head_sha, "selection": selection}
        ),
        selection_json=selection,
        queued_at=datetime.now(UTC),
    )
    session.add_all([receipt, run])
    await session.flush()
    receipt.run_id = run.id
    run.workflow_id = f"histograph/run/{run.id}"
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await session.scalar(
            select(WebhookReceiptRecord).where(
                WebhookReceiptRecord.source == "github",
                WebhookReceiptRecord.delivery_id == delivery_id,
            )
        )
        if existing is None:
            raise
        return await _resume_github_run(session, request, existing)
    return await _resume_github_run(session, request, receipt)


async def _resume_github_run(
    session: AsyncSession,
    request: Request,
    receipt: WebhookReceiptRecord,
) -> dict[str, str]:
    if not receipt.run_id:
        raise HTTPException(status_code=409, detail="GitHub receipt has no durable run")
    run = await session.get(RunRecord, receipt.run_id)
    if run is None:
        raise HTTPException(status_code=409, detail="GitHub receipt run is unavailable")
    context = run.selection_json.get("github")
    if not isinstance(context, dict):
        raise HTTPException(status_code=409, detail="GitHub run context is unavailable")
    required = ("installation_id", "owner", "repository", "head_sha")
    if any(not context.get(key) for key in required):
        raise HTTPException(status_code=409, detail="GitHub run context is incomplete")
    github = _github_client(request)
    try:
        check_run_id = context.get("check_run_id")
        if not isinstance(check_run_id, int):
            check_run_id = await github.ensure_check_run(
                installation_id=int(context["installation_id"]),
                owner=str(context["owner"]),
                repository=str(context["repository"]),
                head_sha=str(context["head_sha"]),
                external_id=run.id,
                details_url=(
                    f"{request.app.state.settings.public_app_url}/projects/"
                    f"{run.project_id}/runs/{run.id}"
                ),
            )
            context["check_run_id"] = check_run_id
            run.selection_json = {**run.selection_json, "github": context}
            await session.commit()
        workflow_id = await request.app.state.orchestrator.start_run(run.id)
        run.workflow_id = workflow_id
        if run.status is RunStatus.ERROR and run.error_code == "workflow_start_failed":
            run.status = RunStatus.QUEUED
            run.error_code = None
            run.error_message = None
            run.completed_at = None
        receipt.status = ReceiptStatus.PROCESSING
        receipt.error_message = None
        await session.commit()
    except Exception as error:
        run.status = RunStatus.ERROR
        run.error_code = "workflow_start_failed"
        run.error_message = str(error)[:4000]
        run.completed_at = datetime.now(UTC)
        receipt.status = ReceiptStatus.FAILED
        receipt.error_message = str(error)[:4000]
        await session.commit()
        raise HTTPException(status_code=503, detail="GitHub run could not be started") from error
    await _supersede_older_runs(session, request.app.state.orchestrator, run)
    return {"status": "processing", "receipt_id": receipt.id, "run_id": run.id}


async def _supersede_older_runs(
    session: AsyncSession,
    orchestrator: Orchestrator,
    run: RunRecord,
) -> None:
    superseded = tuple(
        await session.scalars(
            select(RunRecord).where(
                RunRecord.project_id == run.project_id,
                RunRecord.trigger_reference == run.trigger_reference,
                RunRecord.id != run.id,
                RunRecord.created_at < run.created_at,
                RunRecord.status.in_(
                    [
                        RunStatus.QUEUED,
                        RunStatus.PLANNING,
                        RunStatus.EXECUTING,
                        RunStatus.EVALUATING,
                        RunStatus.DIAGNOSING,
                        RunStatus.REPORTING,
                    ]
                ),
            )
        )
    )
    signalled: list[RunRecord] = []
    for stale in superseded:
        if not stale.workflow_id:
            continue
        try:
            await orchestrator.cancel_run(stale.workflow_id)
        except Exception:
            continue
        signalled.append(stale)
    for stale in signalled:
        stale.cancellation_requested_at = datetime.now(UTC)
        stale.superseded_by_run_id = run.id
    if signalled:
        await session.commit()


async def _ignored_receipt(
    session: AsyncSession,
    repository: RepositoryConnectionRecord,
    payload: dict[str, Any],
    delivery_id: str,
    event_type: str,
) -> dict[str, str]:
    receipt = WebhookReceiptRecord(
        organization_id=repository.organization_id,
        project_id=repository.project_id,
        source="github",
        delivery_id=delivery_id,
        event_type=event_type,
        action=payload.get("action"),
        signature_valid=True,
        payload_json=payload,
        status=ReceiptStatus.IGNORED,
    )
    session.add(receipt)
    await session.commit()
    return {"status": "ignored", "receipt_id": receipt.id}


def _push_changed_files(payload: dict[str, Any]) -> tuple[str, ...]:
    files: list[str] = []
    for commit in payload.get("commits", []):
        if not isinstance(commit, dict):
            continue
        for key in ("added", "modified", "removed"):
            files.extend(item for item in commit.get(key, []) if isinstance(item, str))
    return tuple(dict.fromkeys(files))


def _mapped_assets(configuration: dict, changed_files: tuple[str, ...]) -> tuple[str, ...]:
    assets: list[str] = []
    for mapping in configuration.get("asset_mappings", []):
        if not isinstance(mapping, dict) or not isinstance(mapping.get("pattern"), str):
            continue
        if any(fnmatch(filename, mapping["pattern"]) for filename in changed_files):
            assets.extend(item for item in mapping.get("asset_urns", []) if isinstance(item, str))
    return tuple(dict.fromkeys(assets))


def _github_client(request: Request) -> GitHubAppClient:
    client = request.app.state.github_client
    if client is None:
        raise HTTPException(status_code=503, detail="GitHub App is not configured")
    return client


def _validate_installation_permissions(permissions: dict[str, Any]) -> None:
    required = {
        "checks": {"write"},
        "contents": {"read", "write"},
        "metadata": {"read", "write"},
        "pull_requests": {"read", "write"},
    }
    missing = [
        name
        for name, accepted in required.items()
        if str(permissions.get(name, "none")) not in accepted
    ]
    if missing:
        raise HTTPException(
            status_code=409,
            detail=f"GitHub App installation is missing permissions: {', '.join(missing)}",
        )
