from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from histograph.core.time import ensure_utc, utc_now
from histograph.remediation.types import ApprovalDecision, ExecutionResult, RemediationProposal
from histograph.storage.postgres import PostgresDatabase


class RemediationRepository:
    def __init__(self, database: PostgresDatabase):
        self._database = database

    def propose(self, proposal: RemediationProposal) -> UUID:
        action_id = uuid4()
        with self._database.connection() as connection:
            record = connection.execute(
                """
                INSERT INTO remediation_actions (
                    id, incident_id, action_type, status, adapter, target, evidence, dedupe_key
                ) VALUES (%s, %s, %s, 'proposed', %s, %s, %s, %s)
                ON CONFLICT (dedupe_key) DO UPDATE SET dedupe_key = EXCLUDED.dedupe_key
                RETURNING id
                """,
                (
                    action_id,
                    proposal.incident_id,
                    proposal.action_type,
                    proposal.adapter,
                    Jsonb(proposal.target),
                    Jsonb(proposal.evidence),
                    proposal.dedupe_key,
                ),
            ).fetchone()
            if record is None:
                raise RuntimeError("Remediation proposal did not return an identifier")
            persisted_id = record["id"]
            if persisted_id == action_id:
                self._event(connection, action_id, "proposed", proposal.model_dump(mode="json"))
            connection.commit()
            return persisted_id

    def get(self, action_id: UUID) -> dict[str, Any] | None:
        with self._database.connection() as connection:
            return connection.execute(
                "SELECT * FROM remediation_actions WHERE id = %s", (action_id,)
            ).fetchone()

    def list_for_incident(self, incident_id: UUID) -> list[dict[str, Any]]:
        with self._database.connection() as connection:
            return list(
                connection.execute(
                    """
                    SELECT * FROM remediation_actions
                    WHERE incident_id = %s
                    ORDER BY proposed_at, id
                    """,
                    (incident_id,),
                ).fetchall()
            )

    def events(self, action_id: UUID) -> list[dict[str, Any]]:
        with self._database.connection() as connection:
            return list(
                connection.execute(
                    """
                    SELECT * FROM remediation_action_events
                    WHERE action_id = %s
                    ORDER BY sequence
                    """,
                    (action_id,),
                ).fetchall()
            )

    def approval(self, action_id: UUID) -> dict[str, Any] | None:
        with self._database.connection() as connection:
            return connection.execute(
                "SELECT * FROM remediation_approvals WHERE action_id = %s", (action_id,)
            ).fetchone()

    def decide(
        self,
        action_id: UUID,
        actor_id: str,
        decision: ApprovalDecision,
    ) -> dict[str, Any] | None:
        with self._database.connection() as connection:
            action = connection.execute(
                """
                SELECT actions.*, incidents.status AS incident_status
                FROM remediation_actions AS actions
                JOIN incidents ON incidents.id = actions.incident_id
                WHERE actions.id = %s
                FOR UPDATE OF actions
                """,
                (action_id,),
            ).fetchone()
            if action is None:
                return None
            existing = connection.execute(
                "SELECT * FROM remediation_approvals WHERE action_id = %s", (action_id,)
            ).fetchone()
            if existing is not None:
                if existing["actor_id"] == actor_id and existing["decision"] == decision.decision:
                    decided_status = "approved" if existing["decision"] == "approve" else "rejected"
                    return {
                        **action,
                        "status": decided_status,
                        "approved_at": (
                            existing["decided_at"] if decided_status == "approved" else None
                        ),
                    }
                raise ValueError("This remediation action already has an approval decision")
            if action["status"] != "proposed":
                raise ValueError(
                    f"Remediation action in {action['status']} state cannot be approved or rejected"
                )
            if action["incident_status"] not in {"open", "investigating"}:
                raise ValueError("Remediation cannot be approved for an inactive incident")
            decided_at = utc_now()
            status = "approved" if decision.decision == "approve" else "rejected"
            connection.execute(
                """
                INSERT INTO remediation_approvals (
                    id, action_id, actor_id, decision, reason, decided_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (uuid4(), action_id, actor_id, decision.decision, decision.reason, decided_at),
            )
            connection.execute(
                """
                UPDATE remediation_actions
                SET status = %s, approved_at = CASE WHEN %s = 'approved' THEN %s ELSE NULL END
                WHERE id = %s
                """,
                (status, status, decided_at, action_id),
            )
            self._event(
                connection,
                action_id,
                status,
                {"actor_id": actor_id, "decision": decision.decision, "reason": decision.reason},
            )
            connection.commit()
            return {**action, "status": status, "approved_at": decided_at}

    def approve_and_start_external(
        self,
        action_id: UUID,
        actor_id: str,
        reason: str,
        external_execution_id: str,
        occurred_at: datetime | None = None,
    ) -> dict[str, Any] | None:
        decided_at = ensure_utc(occurred_at) if occurred_at is not None else utc_now()
        accepted = ExecutionResult(
            status="accepted",
            external_execution_id=external_execution_id,
            details={"approval_source": "github_pull_request", "reason": reason},
        )
        with self._database.connection() as connection:
            action = connection.execute(
                """
                SELECT actions.*, incidents.status AS incident_status
                FROM remediation_actions AS actions
                JOIN incidents ON incidents.id = actions.incident_id
                WHERE actions.id = %s
                FOR UPDATE OF actions
                """,
                (action_id,),
            ).fetchone()
            if action is None:
                return None
            if (
                action["status"] in {"executing", "succeeded", "failed"}
                and action.get("external_execution_id") == external_execution_id
            ):
                return action
            if action["status"] != "proposed":
                raise ValueError(
                    f"Remediation action in {action['status']} state cannot be approved by GitHub"
                )
            if action["incident_status"] not in {"open", "investigating"}:
                raise ValueError("Remediation cannot be approved for an inactive incident")
            existing = connection.execute(
                "SELECT * FROM remediation_approvals WHERE action_id = %s", (action_id,)
            ).fetchone()
            if existing is not None:
                raise ValueError("This remediation action already has an approval decision")
            connection.execute(
                """
                INSERT INTO remediation_approvals (
                    id, action_id, actor_id, decision, reason, decided_at
                ) VALUES (%s, %s, %s, 'approve', %s, %s)
                """,
                (uuid4(), action_id, actor_id, reason, decided_at),
            )
            record = connection.execute(
                """
                UPDATE remediation_actions
                SET status = 'executing', approved_at = %s,
                    execution_started_at = %s,
                    external_execution_id = %s,
                    execution_result = %s,
                    attempt_count = attempt_count + 1,
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    last_error = NULL
                WHERE id = %s
                RETURNING *
                """,
                (
                    decided_at,
                    decided_at,
                    external_execution_id,
                    Jsonb(accepted.model_dump(mode="json")),
                    action_id,
                ),
            ).fetchone()
            self._event(
                connection,
                action_id,
                "approved",
                {"actor_id": actor_id, "decision": "approve", "reason": reason},
            )
            self._event(
                connection,
                action_id,
                "execution_started",
                {"source": "github_pull_request", "attempt": action["attempt_count"] + 1},
            )
            self._event(connection, action_id, "execution_accepted", accepted.model_dump())
            connection.commit()
            return record

    def reject_external(self, action_id: UUID, actor_id: str, reason: str) -> dict[str, Any] | None:
        return self.decide(
            action_id,
            actor_id,
            ApprovalDecision(decision="reject", reason=reason),
        )

    def complete_external_execution(
        self,
        action_id: UUID,
        external_execution_id: str,
        status: str,
        details: dict[str, Any],
        occurred_at: datetime | None = None,
    ) -> dict[str, Any] | None:
        current = self.get(action_id)
        if current is None:
            return None
        if current.get("external_execution_id") != external_execution_id:
            raise ValueError("External execution identifier does not match the tracked action")
        if current["status"] in {"succeeded", "failed"}:
            return current
        if current["status"] != "executing":
            raise ValueError("Only an executing remediation action can complete")
        return self.complete_execution(
            action_id,
            ExecutionResult.model_validate(
                {
                    "status": status,
                    "external_execution_id": external_execution_id,
                    "details": details,
                }
            ),
            occurred_at,
        )

    def claim_approved(
        self,
        worker_id: str,
        now: datetime,
        limit: int,
        lease_seconds: int,
    ) -> list[dict[str, Any]]:
        timestamp = ensure_utc(now)
        lease_until = timestamp + timedelta(seconds=lease_seconds)
        with self._database.connection() as connection:
            records = list(
                connection.execute(
                    """
                    WITH candidates AS (
                        SELECT actions.id
                        FROM remediation_actions AS actions
                        JOIN incidents ON incidents.id = actions.incident_id
                        WHERE incidents.status IN ('open', 'investigating')
                          AND (actions.status = 'approved'
                           OR (
                                actions.status = 'executing'
                                AND actions.lease_expires_at IS NOT NULL
                                AND actions.lease_expires_at <= %s
                                AND actions.external_execution_id IS NULL
                           ))
                        ORDER BY actions.approved_at, actions.proposed_at
                        FOR UPDATE OF actions SKIP LOCKED
                        LIMIT %s
                    )
                    UPDATE remediation_actions AS actions
                    SET status = 'executing',
                        execution_started_at = COALESCE(execution_started_at, %s),
                        lease_owner = %s,
                        lease_expires_at = %s,
                        attempt_count = attempt_count + 1,
                        last_error = NULL
                    FROM candidates
                    WHERE actions.id = candidates.id
                    RETURNING actions.*
                    """,
                    (timestamp, limit, timestamp, worker_id, lease_until),
                ).fetchall()
            )
            for record in records:
                self._event(
                    connection,
                    record["id"],
                    "execution_started",
                    {"worker_id": worker_id, "attempt": record["attempt_count"]},
                )
            connection.commit()
            return records

    def complete_execution(
        self,
        action_id: UUID,
        result: ExecutionResult,
        completed_at: datetime | None = None,
    ) -> dict[str, Any] | None:
        status = "executing" if result.status == "accepted" else result.status
        timestamp = ensure_utc(completed_at) if completed_at is not None else utc_now()
        finished_at = timestamp if status in {"succeeded", "failed"} else None
        next_verification = finished_at if status == "succeeded" else None
        with self._database.connection() as connection:
            record = connection.execute(
                """
                UPDATE remediation_actions
                SET status = %s,
                    external_execution_id = %s,
                    execution_result = %s,
                    execution_finished_at = %s,
                    next_verification_at = %s,
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    last_error = CASE WHEN %s = 'failed' THEN %s ELSE NULL END
                WHERE id = %s AND status = 'executing'
                RETURNING *
                """,
                (
                    status,
                    result.external_execution_id,
                    Jsonb(result.model_dump(mode="json")),
                    finished_at,
                    next_verification,
                    status,
                    str(result.details.get("error", "External execution failed")),
                    action_id,
                ),
            ).fetchone()
            if record is not None:
                self._event(
                    connection, action_id, f"execution_{result.status}", result.model_dump()
                )
            connection.commit()
            return record

    def fail_execution(
        self, action_id: UUID, error: str, failed_at: datetime | None = None
    ) -> None:
        result = ExecutionResult(
            status="failed",
            external_execution_id=f"histograph-error-{action_id}",
            details={"error": error},
        )
        self.complete_execution(action_id, result, failed_at)

    def claim_recovery_due(
        self,
        worker_id: str,
        now: datetime,
        limit: int,
        lease_seconds: int,
    ) -> list[dict[str, Any]]:
        timestamp = ensure_utc(now)
        lease_until = timestamp + timedelta(seconds=lease_seconds)
        with self._database.connection() as connection:
            records = list(
                connection.execute(
                    """
                    WITH candidates AS (
                        SELECT actions.id
                        FROM remediation_actions AS actions
                        JOIN incidents ON incidents.id = actions.incident_id
                        WHERE incidents.status IN ('open', 'investigating')
                          AND actions.status = 'succeeded'
                          AND actions.recovery_verified_at IS NULL
                          AND actions.next_verification_at <= %s
                          AND (
                              actions.lease_expires_at IS NULL
                              OR actions.lease_expires_at <= %s
                          )
                        ORDER BY actions.next_verification_at, actions.execution_finished_at
                        FOR UPDATE OF actions SKIP LOCKED
                        LIMIT %s
                    )
                    UPDATE remediation_actions AS actions
                    SET lease_owner = %s, lease_expires_at = %s
                    FROM candidates
                    WHERE actions.id = candidates.id
                    RETURNING actions.*
                    """,
                    (timestamp, timestamp, limit, worker_id, lease_until),
                ).fetchall()
            )
            connection.commit()
            return records

    def cancel_for_incident(self, incident_id: UUID, reason: str) -> int:
        with self._database.connection() as connection:
            records = list(
                connection.execute(
                    """
                    UPDATE remediation_actions
                    SET status = 'cancelled',
                        lease_owner = NULL,
                        lease_expires_at = NULL,
                        last_error = %s
                    WHERE incident_id = %s AND status IN ('proposed', 'approved')
                    RETURNING id
                    """,
                    (reason, incident_id),
                ).fetchall()
            )
            for record in records:
                self._event(connection, record["id"], "cancelled", {"reason": reason})
            connection.commit()
            return len(records)

    def reschedule_recovery(self, action_id: UUID, when: datetime, error: str | None) -> None:
        with self._database.connection() as connection:
            connection.execute(
                """
                UPDATE remediation_actions
                SET next_verification_at = %s,
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    last_error = %s
                WHERE id = %s AND status = 'succeeded' AND recovery_verified_at IS NULL
                """,
                (ensure_utc(when), error, action_id),
            )
            connection.commit()

    def mark_recovery_verified(self, action_id: UUID, verified_at: datetime) -> None:
        with self._database.connection() as connection:
            connection.execute(
                """
                UPDATE remediation_actions
                SET recovery_verified_at = %s,
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    last_error = NULL
                WHERE id = %s
                """,
                (ensure_utc(verified_at), action_id),
            )
            self._event(
                connection,
                action_id,
                "recovery_verified",
                {"verified_at": ensure_utc(verified_at).isoformat()},
            )
            connection.commit()

    @staticmethod
    def _event(connection, action_id: UUID, event_type: str, details: dict[str, Any]) -> None:
        connection.execute(
            """
            INSERT INTO remediation_action_events (id, action_id, event_type, details)
            VALUES (%s, %s, %s, %s)
            """,
            (uuid4(), action_id, event_type, Jsonb(details)),
        )
