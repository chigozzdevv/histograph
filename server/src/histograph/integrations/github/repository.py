from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from histograph.changes.types import Change
from histograph.core.time import ensure_utc
from histograph.deployments.types import Deployment
from histograph.integrations.github.types import (
    CreatedPullRequest,
    GitHubConnectionCreate,
    ModelDeploymentManifest,
    ResolvedModelInterface,
)
from histograph.storage.postgres import PostgresDatabase


class GitOpsRepository:
    def __init__(self, database: PostgresDatabase):
        self._database = database

    def save_connection(self, connection: GitHubConnectionCreate) -> UUID:
        connection_id = uuid4()
        with self._database.connection() as database_connection:
            record = database_connection.execute(
                """
                INSERT INTO github_connections (
                    id, installation_id, repository_owner, repository_name, branch, manifest_path
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (repository_owner, repository_name, branch, manifest_path)
                DO UPDATE SET
                    installation_id = EXCLUDED.installation_id,
                    enabled = TRUE,
                    updated_at = NOW()
                RETURNING id
                """,
                (
                    connection_id,
                    connection.installation_id,
                    connection.repository_owner,
                    connection.repository_name,
                    connection.branch,
                    connection.manifest_path,
                ),
            ).fetchone()
            database_connection.commit()
        if record is None:
            raise RuntimeError("GitHub connection persistence did not return an identifier")
        return record["id"]

    def get_connection(self, connection_id: UUID) -> dict[str, Any] | None:
        with self._database.connection() as connection:
            return connection.execute(
                "SELECT * FROM github_connections WHERE id = %s", (connection_id,)
            ).fetchone()

    def list_connections(self) -> list[dict[str, Any]]:
        with self._database.connection() as connection:
            return list(
                connection.execute(
                    """
                    SELECT id, repository_owner, repository_name, branch, manifest_path,
                           enabled, last_synced_at, last_error, created_at, updated_at
                    FROM github_connections
                    ORDER BY created_at, id
                    """
                ).fetchall()
            )

    def connections_for_repository_branch(
        self, owner: str, repository: str, branch: str
    ) -> list[dict[str, Any]]:
        with self._database.connection() as connection:
            return list(
                connection.execute(
                    """
                    SELECT * FROM github_connections
                    WHERE repository_owner = %s
                      AND repository_name = %s
                      AND branch = %s
                      AND enabled = TRUE
                    ORDER BY created_at, id
                    """,
                    (owner, repository, branch),
                ).fetchall()
            )

    def record_sync(
        self,
        connection_id: UUID,
        manifest: ModelDeploymentManifest,
        *,
        revision: str,
        manifest_sha: str,
        content: str,
        interface: ResolvedModelInterface | None = None,
    ) -> UUID:
        deployment_id = uuid4()
        payload = manifest.model_dump(mode="json", by_alias=True, exclude_none=True)
        spec = manifest.spec
        with self._database.connection() as connection:
            record = connection.execute(
                """
                INSERT INTO gitops_deployments (
                    id, connection_id, deployment, model, environment, provider,
                    datahub_model_urn, desired_revision, manifest_sha,
                    manifest_content, manifest, input_schema, output_schema, examples
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (connection_id, deployment, environment)
                DO UPDATE SET
                    model = EXCLUDED.model,
                    provider = EXCLUDED.provider,
                    datahub_model_urn = EXCLUDED.datahub_model_urn,
                    desired_revision = EXCLUDED.desired_revision,
                    manifest_sha = EXCLUDED.manifest_sha,
                    manifest_content = EXCLUDED.manifest_content,
                    manifest = EXCLUDED.manifest,
                    input_schema = EXCLUDED.input_schema,
                    output_schema = EXCLUDED.output_schema,
                    examples = EXCLUDED.examples,
                    sync_status = CASE
                        WHEN gitops_deployments.observed_state IS NULL THEN 'desired_only'
                        ELSE 'out_of_sync'
                    END,
                    updated_at = NOW()
                RETURNING id
                """,
                (
                    deployment_id,
                    connection_id,
                    manifest.metadata.name,
                    spec.model.name,
                    spec.environment,
                    spec.runtime.provider,
                    spec.model.datahub_urn,
                    revision,
                    manifest_sha,
                    content,
                    Jsonb(payload),
                    Jsonb(interface.input_schema) if interface is not None else None,
                    Jsonb(interface.output_schema) if interface is not None else None,
                    Jsonb(interface.examples) if interface is not None else None,
                ),
            ).fetchone()
            connection.execute(
                """
                UPDATE github_connections
                SET last_synced_at = NOW(), last_error = NULL, updated_at = NOW()
                WHERE id = %s
                """,
                (connection_id,),
            )
            connection.commit()
        if record is None:
            raise RuntimeError("GitOps deployment persistence did not return an identifier")
        persisted_id = record["id"]
        self._refresh_sync_status(persisted_id)
        return persisted_id

    def fail_sync(self, connection_id: UUID, error: str) -> None:
        with self._database.connection() as connection:
            connection.execute(
                """
                UPDATE github_connections
                SET last_error = %s, updated_at = NOW()
                WHERE id = %s
                """,
                (error, connection_id),
            )
            connection.commit()

    def list_deployments(self) -> list[dict[str, Any]]:
        with self._database.connection() as connection:
            return list(
                connection.execute(
                    """
                    SELECT deployments.*,
                           connections.repository_owner,
                           connections.repository_name,
                           connections.branch,
                           connections.manifest_path
                    FROM gitops_deployments AS deployments
                    JOIN github_connections AS connections
                      ON connections.id = deployments.connection_id
                    ORDER BY deployments.environment, deployments.deployment
                    """
                ).fetchall()
            )

    def get_deployment(self, deployment_id: UUID) -> dict[str, Any] | None:
        with self._database.connection() as connection:
            return connection.execute(
                """
                SELECT deployments.*,
                       connections.installation_id,
                       connections.repository_owner,
                       connections.repository_name,
                       connections.branch,
                       connections.manifest_path,
                       connections.enabled AS connection_enabled
                FROM gitops_deployments AS deployments
                JOIN github_connections AS connections
                  ON connections.id = deployments.connection_id
                WHERE deployments.id = %s
                """,
                (deployment_id,),
            ).fetchone()

    def adapter_for_target(self, target: dict[str, Any]) -> str | None:
        deployment = target.get("deployment")
        model = target.get("model")
        environment = target.get("environment", "production")
        if not all(isinstance(value, str) and value for value in (deployment, model, environment)):
            return None
        with self._database.connection() as connection:
            record = connection.execute(
                """
                SELECT deployments.id
                FROM gitops_deployments AS deployments
                JOIN github_connections AS connections
                  ON connections.id = deployments.connection_id
                WHERE deployments.deployment = %s
                  AND deployments.model = %s
                  AND deployments.environment = %s
                  AND connections.enabled = TRUE
                ORDER BY deployments.updated_at DESC
                LIMIT 1
                """,
                (deployment, model, environment),
            ).fetchone()
        return "github_pr" if record is not None else None

    def claim_pull_request_proposals(
        self, worker_id: str, now: datetime, limit: int, lease_seconds: int
    ) -> list[dict[str, Any]]:
        timestamp = ensure_utc(now)
        lease_until = timestamp + timedelta(seconds=lease_seconds)
        claimed: list[dict[str, Any]] = []
        with self._database.connection() as connection:
            candidates = list(
                connection.execute(
                    """
                    SELECT actions.*,
                           target_deployment.id AS gitops_deployment_id,
                           target_deployment.connection_id,
                           target_deployment.manifest_content,
                           target_deployment.manifest,
                           target_deployment.manifest_sha,
                           target_deployment.desired_revision,
                           connections.installation_id,
                           connections.repository_owner,
                           connections.repository_name,
                           connections.branch,
                           connections.manifest_path,
                           pull_requests.status AS pull_request_status
                    FROM remediation_actions AS actions
                    JOIN LATERAL (
                        SELECT deployments.*
                        FROM gitops_deployments AS deployments
                        JOIN github_connections AS candidate_connections
                          ON candidate_connections.id = deployments.connection_id
                        WHERE deployments.deployment = actions.target->>'deployment'
                          AND deployments.model = actions.target->>'model'
                          AND deployments.environment = COALESCE(
                              actions.target->>'environment', 'production'
                          )
                          AND candidate_connections.enabled = TRUE
                        ORDER BY deployments.updated_at DESC
                        LIMIT 1
                    ) AS target_deployment ON TRUE
                    JOIN github_connections AS connections
                      ON connections.id = target_deployment.connection_id
                    LEFT JOIN gitops_pull_requests AS pull_requests
                      ON pull_requests.action_id = actions.id
                    WHERE actions.status = 'proposed'
                      AND actions.adapter = 'github_pr'
                      AND (
                          pull_requests.action_id IS NULL
                          OR (
                              pull_requests.status IN ('creating', 'failed')
                              AND pull_requests.next_attempt_at <= %s
                              AND (
                                  pull_requests.lease_expires_at IS NULL
                                  OR pull_requests.lease_expires_at <= %s
                              )
                          )
                      )
                    ORDER BY actions.proposed_at, actions.id
                    FOR UPDATE OF actions SKIP LOCKED
                    LIMIT %s
                    """,
                    (timestamp, timestamp, limit),
                ).fetchall()
            )
            for candidate in candidates:
                head_branch = f"histograph/rollback-{candidate['id']}"
                connection.execute(
                    """
                    INSERT INTO gitops_pull_requests (
                        action_id, connection_id, deployment_id, status,
                        head_branch, base_branch, attempt_count,
                        lease_owner, lease_expires_at
                    ) VALUES (%s, %s, %s, 'creating', %s, %s, 1, %s, %s)
                    ON CONFLICT (action_id) DO UPDATE SET
                        status = 'creating',
                        attempt_count = gitops_pull_requests.attempt_count + 1,
                        lease_owner = EXCLUDED.lease_owner,
                        lease_expires_at = EXCLUDED.lease_expires_at,
                        next_attempt_at = EXCLUDED.next_attempt_at,
                        last_error = NULL,
                        updated_at = NOW()
                    """,
                    (
                        candidate["id"],
                        candidate["connection_id"],
                        candidate["gitops_deployment_id"],
                        head_branch,
                        candidate["branch"],
                        worker_id,
                        lease_until,
                    ),
                )
                claimed.append({**candidate, "head_branch": head_branch})
            connection.commit()
        return claimed

    def complete_pull_request(self, action_id: UUID, result: CreatedPullRequest) -> None:
        with self._database.connection() as connection:
            connection.execute(
                """
                UPDATE gitops_pull_requests
                SET status = 'open',
                    head_branch = %s,
                    pull_request_number = %s,
                    pull_request_url = %s,
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    last_error = NULL,
                    updated_at = NOW()
                WHERE action_id = %s
                """,
                (result.head_branch, result.number, result.url, action_id),
            )
            connection.commit()

    def fail_pull_request(
        self,
        action_id: UUID,
        error: str,
        failed_at: datetime,
        retry_seconds: int,
    ) -> None:
        retry_at = ensure_utc(failed_at) + timedelta(seconds=retry_seconds)
        with self._database.connection() as connection:
            connection.execute(
                """
                UPDATE gitops_pull_requests
                SET status = 'failed',
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    next_attempt_at = %s,
                    last_error = %s,
                    updated_at = NOW()
                WHERE action_id = %s
                """,
                (retry_at, error, action_id),
            )
            connection.commit()

    def cancel_stale_proposal(self, action_id: UUID, reason: str) -> None:
        with self._database.connection() as connection:
            record = connection.execute(
                """
                UPDATE remediation_actions
                SET status = 'cancelled', last_error = %s
                WHERE id = %s AND status = 'proposed'
                RETURNING id
                """,
                (reason, action_id),
            ).fetchone()
            if record is not None:
                connection.execute(
                    """
                    UPDATE gitops_pull_requests
                    SET status = 'failed', lease_owner = NULL, lease_expires_at = NULL,
                        last_error = %s, updated_at = NOW()
                    WHERE action_id = %s
                    """,
                    (reason, action_id),
                )
                connection.execute(
                    """
                    INSERT INTO remediation_action_events (id, action_id, event_type, details)
                    VALUES (%s, %s, 'cancelled', %s)
                    """,
                    (uuid4(), action_id, Jsonb({"reason": reason})),
                )
            connection.commit()

    def pull_request_for_action(self, action_id: UUID) -> dict[str, Any] | None:
        with self._database.connection() as connection:
            return connection.execute(
                "SELECT * FROM gitops_pull_requests WHERE action_id = %s", (action_id,)
            ).fetchone()

    def mark_pull_request_merged(
        self,
        owner: str,
        repository: str,
        number: int,
        merge_sha: str,
        actor: str,
        merged_at: datetime,
    ) -> dict[str, Any] | None:
        with self._database.connection() as connection:
            record = connection.execute(
                """
                UPDATE gitops_pull_requests AS pull_requests
                SET status = 'merged', merge_sha = %s, approved_by = %s,
                    merged_at = %s, updated_at = NOW()
                FROM github_connections AS connections
                WHERE pull_requests.connection_id = connections.id
                  AND connections.repository_owner = %s
                  AND connections.repository_name = %s
                  AND pull_requests.pull_request_number = %s
                  AND pull_requests.status IN ('open', 'merged')
                RETURNING pull_requests.*
                """,
                (merge_sha, actor, ensure_utc(merged_at), owner, repository, number),
            ).fetchone()
            connection.commit()
            return record

    def mark_pull_request_closed(
        self, owner: str, repository: str, number: int
    ) -> dict[str, Any] | None:
        with self._database.connection() as connection:
            record = connection.execute(
                """
                UPDATE gitops_pull_requests AS pull_requests
                SET status = 'closed', updated_at = NOW()
                FROM github_connections AS connections
                WHERE pull_requests.connection_id = connections.id
                  AND connections.repository_owner = %s
                  AND connections.repository_name = %s
                  AND pull_requests.pull_request_number = %s
                  AND pull_requests.status IN ('open', 'closed')
                RETURNING pull_requests.*
                """,
                (owner, repository, number),
            ).fetchone()
            connection.commit()
            return record

    def action_for_revision(
        self, owner: str, repository: str, revision: str
    ) -> dict[str, Any] | None:
        with self._database.connection() as connection:
            return connection.execute(
                """
                SELECT pull_requests.*, actions.status AS action_status,
                       actions.external_execution_id
                FROM gitops_pull_requests AS pull_requests
                JOIN github_connections AS connections
                  ON connections.id = pull_requests.connection_id
                JOIN remediation_actions AS actions ON actions.id = pull_requests.action_id
                WHERE connections.repository_owner = %s
                  AND connections.repository_name = %s
                  AND pull_requests.merge_sha = %s
                ORDER BY pull_requests.merged_at DESC
                LIMIT 1
                """,
                (owner, repository, revision),
            ).fetchone()

    def begin_delivery(self, delivery_id: str, event_type: str) -> bool:
        with self._database.connection() as connection:
            record = connection.execute(
                """
                INSERT INTO github_webhook_deliveries (delivery_id, event_type, status)
                VALUES (%s, %s, 'processing')
                ON CONFLICT (delivery_id) DO UPDATE SET
                    status = 'processing',
                    event_type = EXCLUDED.event_type,
                    attempt_count = github_webhook_deliveries.attempt_count + 1,
                    last_attempt_at = NOW(),
                    last_error = NULL,
                    processed_at = NULL
                WHERE github_webhook_deliveries.status = 'failed'
                   OR (
                       github_webhook_deliveries.status = 'processing'
                       AND github_webhook_deliveries.last_attempt_at <= NOW() - INTERVAL '5 minutes'
                   )
                RETURNING delivery_id
                """,
                (delivery_id, event_type),
            ).fetchone()
            connection.commit()
            return record is not None

    def complete_delivery(self, delivery_id: str) -> None:
        self._finish_delivery(delivery_id, "completed", None)

    def fail_delivery(self, delivery_id: str, error: str) -> None:
        self._finish_delivery(delivery_id, "failed", error)

    def _finish_delivery(self, delivery_id: str, status: str, error: str | None) -> None:
        with self._database.connection() as connection:
            connection.execute(
                """
                UPDATE github_webhook_deliveries
                SET status = %s, last_error = %s, processed_at = NOW()
                WHERE delivery_id = %s
                """,
                (status, error, delivery_id),
            )
            connection.commit()

    def observe_deployment(self, deployment: Deployment) -> None:
        with self._database.connection() as connection:
            records = list(
                connection.execute(
                    """
                    SELECT * FROM gitops_deployments
                    WHERE deployment = %s AND model = %s AND environment = %s
                    FOR UPDATE
                    """,
                    (deployment.deployment, deployment.model, deployment.environment),
                ).fetchall()
            )
            for record in records:
                state = dict(record.get("observed_state") or {})
                versions = dict(state.get("model_versions") or {})
                versions[deployment.version] = deployment.model_dump(mode="json")
                state["model_versions"] = versions
                sync_status = _sync_status(record["manifest"], state)
                connection.execute(
                    """
                    UPDATE gitops_deployments
                    SET observed_state = %s, observed_at = %s,
                        sync_status = %s, updated_at = NOW()
                    WHERE id = %s
                    """,
                    (Jsonb(state), deployment.occurred_at, sync_status, record["id"]),
                )
            connection.commit()

    def observe_change(self, change: Change) -> None:
        with self._database.connection() as connection:
            records = list(
                connection.execute(
                    """
                    SELECT * FROM gitops_deployments
                    WHERE environment = %s
                      AND manifest @> %s
                    FOR UPDATE
                    """,
                    (
                        change.environment,
                        Jsonb({"spec": {"features": [{"assetUrn": change.asset_urn}]}}),
                    ),
                ).fetchall()
            )
            for record in records:
                state = dict(record.get("observed_state") or {})
                features = dict(state.get("features") or {})
                features[change.asset_urn] = change.model_dump(mode="json")
                state["features"] = features
                sync_status = _sync_status(record["manifest"], state)
                connection.execute(
                    """
                    UPDATE gitops_deployments
                    SET observed_state = %s, observed_at = %s,
                        sync_status = %s, updated_at = NOW()
                    WHERE id = %s
                    """,
                    (Jsonb(state), change.occurred_at, sync_status, record["id"]),
                )
            connection.commit()

    def _refresh_sync_status(self, deployment_id: UUID) -> None:
        with self._database.connection() as connection:
            record = connection.execute(
                "SELECT manifest, observed_state FROM gitops_deployments WHERE id = %s",
                (deployment_id,),
            ).fetchone()
            if record is None:
                return
            status = _sync_status(record["manifest"], record.get("observed_state") or {})
            connection.execute(
                "UPDATE gitops_deployments SET sync_status = %s WHERE id = %s",
                (status, deployment_id),
            )
            connection.commit()


def _sync_status(manifest: dict[str, Any], observed: dict[str, Any]) -> str:
    if not observed:
        return "desired_only"
    spec = manifest.get("spec") if isinstance(manifest, dict) else None
    if not isinstance(spec, dict):
        return "out_of_sync"
    observed_versions = observed.get("model_versions")
    if not isinstance(observed_versions, dict):
        return "out_of_sync"
    desired_releases = [spec.get("stable"), spec.get("candidate")]
    for desired in desired_releases:
        if not isinstance(desired, dict):
            continue
        version = desired.get("version")
        actual = observed_versions.get(version)
        if not isinstance(actual, dict):
            return "out_of_sync"
        if float(actual.get("traffic_percentage", -1)) != float(
            desired.get("trafficPercentage", -2)
        ):
            return "out_of_sync"
        desired_traffic = float(desired.get("trafficPercentage", -1))
        actual_status = actual.get("status")
        if desired_traffic == 0 and actual_status not in {"stopped", "rolled_back"}:
            return "out_of_sync"
        if desired_traffic > 0 and actual_status not in {"active", "monitoring"}:
            return "out_of_sync"
    observed_features = observed.get("features") or {}
    for feature in spec.get("features", []) or []:
        if not isinstance(feature, dict):
            continue
        actual = observed_features.get(feature.get("assetUrn"))
        if not isinstance(actual, dict) or actual.get("version") != feature.get("version"):
            return "out_of_sync"
    return "in_sync"
