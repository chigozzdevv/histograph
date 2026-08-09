from typing import Any

from histograph.storage.postgres import PostgresDatabase


class ProductRepository:
    def __init__(self, database: PostgresDatabase):
        self._database = database

    def overview(self) -> dict[str, Any]:
        with self._database.connection() as connection:
            counts = connection.execute(
                """
                SELECT
                    (SELECT count(*) FROM gitops_deployments) AS deployments,
                    (SELECT count(*) FROM monitors WHERE enabled = TRUE) AS active_monitors,
                    (SELECT count(*) FROM incidents
                     WHERE status IN ('open', 'investigating')) AS active_incidents,
                    (SELECT count(*) FROM remediation_actions
                     WHERE status = 'proposed') AS pending_approvals,
                    (SELECT count(*) FROM github_connections
                     WHERE enabled = TRUE) AS github_connections
                """
            ).fetchone()
            latest_incident = connection.execute(
                """
                SELECT id, model, version, status, severity, summary, created_at, resolved_at
                FROM incidents ORDER BY created_at DESC LIMIT 1
                """
            ).fetchone()
            latest_run = connection.execute(
                """
                SELECT id, deployment_id, status, stage, monitor_id, incident_id, action_id,
                       created_at, updated_at, finished_at, last_error
                FROM demo_runs ORDER BY created_at DESC LIMIT 1
                """
            ).fetchone()
        return {
            "counts": counts or {},
            "latest_incident": latest_incident,
            "latest_demo_run": latest_run,
        }

    def activity(self, limit: int) -> list[dict[str, Any]]:
        with self._database.connection() as connection:
            return list(
                connection.execute(
                    """
                    SELECT * FROM (
                        SELECT incident_events.id,
                               'incident'::text AS category,
                               incident_events.event_type,
                               incident_events.incident_id AS entity_id,
                               incident_events.details,
                               incident_events.created_at
                        FROM incident_events
                        UNION ALL
                        SELECT remediation_action_events.id,
                               'remediation'::text,
                               remediation_action_events.event_type,
                               remediation_action_events.action_id,
                               remediation_action_events.details,
                               remediation_action_events.created_at
                        FROM remediation_action_events
                        UNION ALL
                        SELECT deployments.id,
                               'deployment'::text,
                               'deployment_observed'::text,
                               deployments.id,
                               jsonb_build_object(
                                   'deployment', deployments.deployment,
                                   'model', deployments.model,
                                   'version', deployments.version,
                                   'status', deployments.status,
                                   'traffic_percentage', deployments.traffic_percentage
                               ),
                               deployments.occurred_at
                        FROM deployments
                        UNION ALL
                        SELECT changes.id,
                               'change'::text,
                               'change_observed'::text,
                               changes.id,
                               jsonb_build_object(
                                   'asset_urn', changes.asset_urn,
                                   'asset_name', changes.asset_name,
                                   'version', changes.version,
                                   'change_type', changes.change_type,
                                   'status', changes.status
                               ),
                               changes.occurred_at
                        FROM changes
                    ) AS activity
                    ORDER BY created_at DESC, id
                    LIMIT %s
                    """,
                    (limit,),
                ).fetchall()
            )
