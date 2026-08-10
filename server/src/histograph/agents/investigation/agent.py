import json
from typing import Any, Protocol
from uuid import UUID


class InvestigationControl(Protocol):
    def get(self, incident_id: UUID) -> dict[str, Any] | None: ...

    def update(self, incident_id: UUID, summary: str, evidence: dict[str, Any]) -> bool: ...


class InvestigationDataHub(Protocol):
    async def collect_context(self, model_urn: str, max_hops: int) -> dict[str, Any]: ...

    async def save_investigation(
        self, title: str, content: str, related_assets: list[str]
    ) -> dict[str, Any]: ...


class InvestigationReleaseHistory(Protocol):
    def collect(self, incident: dict[str, Any], asset_urns: list[str]) -> dict[str, Any]: ...


class InvestigationAgent:
    def __init__(
        self,
        control: InvestigationControl,
        datahub: InvestigationDataHub,
        release_history: InvestigationReleaseHistory | None = None,
    ):
        self._control = control
        self._datahub = datahub
        self._release_history = release_history

    async def investigate(
        self,
        incident_id: UUID,
        model_urn: str,
        max_hops: int = 3,
        write_back: bool = False,
    ) -> dict[str, Any]:
        incident = self._control.get(incident_id)
        if incident is None:
            raise LookupError("Incident not found")

        context = await self._datahub.collect_context(model_urn, max_hops=max_hops)
        releases = (
            self._release_history.collect(incident, _asset_urns(context))
            if self._release_history is not None
            else {}
        )
        report = _build_report(incident, model_urn, context, releases)
        writeback: dict[str, Any] | None = None
        if write_back:
            writeback = await self._datahub.save_investigation(
                title=f"Histograph investigation: {incident['model']} {incident['version']}",
                content=_as_markdown(report),
                related_assets=_asset_urns(context),
            )

        evidence = {
            **(incident.get("evidence") or {}),
            "root_cause_status": report["status"],
            "investigation": report,
            "datahub": {
                "status": "written_back" if writeback is not None else "investigated",
                "model_urn": model_urn,
                "tool_trace": context.get("tool_trace", []),
                "writeback": writeback,
            },
        }
        self._control.update(incident_id, report["summary"], evidence)
        return {"incident_id": incident_id, **report, "writeback": writeback}


def _build_report(
    incident: dict[str, Any],
    model_urn: str,
    context: dict[str, Any],
    releases: dict[str, Any] | None = None,
) -> dict[str, Any]:
    upstream = _lineage_entities(context.get("upstream"))
    downstream = _lineage_entities(context.get("downstream"))
    model_entities = _entity_summaries(context.get("model"))
    related = _entity_summaries(context.get("related_entities"))
    owners = sorted(
        {owner for entity in [*model_entities, *related] for owner in entity.get("owners", [])}
    )
    incident_evidence = incident.get("evidence") or {}
    detection = incident_evidence.get("detection", {})
    recovery = incident_evidence.get("recovery")
    metric = incident.get("metric", "signal")
    model = incident.get("model", "model")
    version = incident.get("version", "unknown")
    release_evidence = releases or {}
    changes = _dict_items(release_evidence.get("changes"))
    deployments = _dict_items(release_evidence.get("deployments"))
    feature = detection.get("feature") if isinstance(detection, dict) else None
    lineage_changes = [change for change in changes if change.get("lineage_match") is True]
    matching_changes = [
        change for change in lineage_changes if _change_matches_feature(change, feature)
    ]
    candidate_deployments = [
        deployment for deployment in deployments if deployment.get("version") == version
    ]
    candidate_deployment = candidate_deployments[0] if candidate_deployments else None
    recovery_verified = _recovery_verified(incident)
    rolled_back_change = any(
        change.get("status") == "rolled_back" or change.get("change_type") == "rollback"
        for change in matching_changes
    )
    rolled_back_deployment = bool(
        candidate_deployment is not None
        and candidate_deployment.get("status") in {"stopped", "rolled_back"}
        and float(candidate_deployment.get("traffic_percentage", -1)) == 0
    )

    if matching_changes:
        release = next(
            (
                change
                for change in matching_changes
                if change.get("status") == "applied" and change.get("change_type") != "rollback"
            ),
            matching_changes[0],
        )
        status = (
            "confirmed_cause"
            if recovery_verified and rolled_back_change
            else "probable_cause"
            if not candidate_deployments
            else "correlated_change"
        )
        lineage_status = "mapped"
        summary = (
            f"{release.get('asset_name', 'An upstream asset')} {release.get('version', '')} "
            f"changed before the {metric} signal for {model} {version}. The changed asset is "
            "in the model's DataHub lineage"
            + (
                " and verified recovery followed its rollback."
                if status == "confirmed_cause"
                else "; rollback is not yet verified."
            )
        )
        root_cause = {
            "kind": "upstream_release",
            "asset_urn": release.get("asset_urn"),
            "asset_name": release.get("asset_name"),
            "version": release.get("version"),
            "change_type": release.get("change_type"),
            "occurred_at": release.get("occurred_at"),
            "rollback_observed": rolled_back_change,
        }
    elif candidate_deployment is not None and detection.get("comparison_type") == (
        "candidate_against_reference_version"
    ):
        deployment = candidate_deployment
        active_state = deployment.get("evidence_basis") == "active_deployment_state"
        status = (
            "confirmed_cause" if recovery_verified and rolled_back_deployment else "probable_cause"
        )
        lineage_status = "mapped" if upstream or downstream else "unavailable"
        summary = (
            f"Model {model} {version} degraded against its same-window reference "
            + (
                f"while the runtime-confirmed {deployment.get('strategy', 'deployment')} "
                "candidate was actively serving"
                if active_state
                else f"after a {deployment.get('strategy', 'deployment')} release"
            )
            + (
                ", and verified recovery followed rollback."
                if status == "confirmed_cause"
                else "; rollback is not yet verified."
            )
        )
        root_cause = {
            "kind": "model_release",
            "deployment": deployment.get("deployment"),
            "version": deployment.get("version"),
            "strategy": deployment.get("strategy"),
            "status": deployment.get("status"),
            "traffic_percentage": deployment.get("traffic_percentage"),
            "occurred_at": deployment.get("occurred_at"),
            "evidence_basis": deployment.get("evidence_basis", "release_window"),
            "rollback_observed": rolled_back_deployment,
        }
    elif not upstream and not downstream:
        status = "insufficient_evidence"
        lineage_status = "unavailable"
        summary = (
            f"DataHub returned no lineage for {model} {version}; Histograph cannot establish "
            "a dependency-level explanation or blast radius."
        )
        root_cause = None
    else:
        status = "insufficient_evidence"
        lineage_status = "mapped"
        summary = (
            f"Histograph mapped {len(upstream)} upstream dependencies and "
            f"{len(downstream)} downstream consumers for {model} {version}. "
            f"The {metric} signal has not been tied to a specific dependency change; "
            "lineage alone is not root-cause evidence."
        )
        root_cause = None

    return {
        "status": status,
        "lineage_status": lineage_status,
        "summary": summary,
        "model": {"name": model, "version": version, "urn": model_urn},
        "trigger": {
            "signal": incident.get("signal"),
            "metric": metric,
            "detection": detection,
        },
        "hypotheses": [
            {
                "id": "release_correlation",
                "status": (
                    "confirmed"
                    if status == "confirmed_cause"
                    else "supported"
                    if status in {"probable_cause", "correlated_change"}
                    else "unsupported"
                ),
                "statement": (
                    "A lineage-matched release occurred before the signal and was evaluated "
                    "against model deployment and recovery evidence."
                ),
                "evidence_urns": sorted(
                    {
                        change["asset_urn"]
                        for change in matching_changes
                        if isinstance(change.get("asset_urn"), str)
                    }
                ),
            },
            {
                "id": "upstream_dependency",
                "status": "candidate" if upstream else "unsupported",
                "statement": (
                    "An upstream dependency may explain the detected signal; corroborate "
                    "with the dependency's schema, quality, or change history."
                ),
                "evidence_urns": [entity["urn"] for entity in upstream],
            },
            {
                "id": "downstream_blast_radius",
                "status": "mapped" if downstream else "none_found",
                "statement": (
                    "The downstream lineage identifies assets that may be affected by the incident."
                ),
                "evidence_urns": [entity["urn"] for entity in downstream],
            },
        ],
        "lineage": {
            "upstream": upstream,
            "downstream": downstream,
            "related_entities": related,
        },
        "owners": owners,
        "root_cause": root_cause,
        "release_evidence": release_evidence,
        "recovery": recovery if isinstance(recovery, dict) else None,
        "evidence": {
            "datahub_model_urn": model_urn,
            "tools": context.get("tool_trace", []),
            "raw_context": context,
        },
        "recommended_action": _recommended_action(status, root_cause),
    }


def _dict_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _change_matches_feature(change: dict[str, Any], feature: Any) -> bool:
    if not isinstance(feature, str):
        return False
    metadata = change.get("metadata")
    changed_features = metadata.get("changed_features") if isinstance(metadata, dict) else None
    return isinstance(changed_features, list) and feature in changed_features


def _recovery_verified(incident: dict[str, Any]) -> bool:
    evidence = incident.get("evidence")
    recovery = evidence.get("recovery") if isinstance(evidence, dict) else None
    return isinstance(recovery, dict) and recovery.get("status") == "verified"


def _recommended_action(status: str, root_cause: dict[str, Any] | None) -> str:
    if status == "confirmed_cause":
        return "Preserve the verified rollback and resolution evidence in Histograph and DataHub."
    if status == "probable_cause" and root_cause is not None:
        return (
            "Keep the incident open and request approval to roll back the identified release; "
            "resolve only after fresh feature and performance checks pass."
        )
    if status == "correlated_change":
        return (
            "Keep the incident open and isolate the upstream and model releases with a control "
            "comparison before approving either rollback."
        )
    return (
        "Keep the incident open, inspect the candidate upstream assets, and only approve "
        "rollback or retraining after a change or quality signal is corroborated."
    )


def _lineage_entities(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []

    search_results: Any = payload.get("searchResults")
    if search_results is None:
        for direction in ("upstreams", "downstreams"):
            direction_payload = payload.get(direction)
            if isinstance(direction_payload, dict):
                search_results = direction_payload.get("searchResults")
                if search_results is not None:
                    break

    if not isinstance(search_results, list):
        return []

    entities: list[dict[str, Any]] = []
    for item in search_results:
        if not isinstance(item, dict):
            continue
        entity = item.get("entity")
        if not isinstance(entity, dict) or not isinstance(entity.get("urn"), str):
            continue
        entities.append(
            {
                "urn": entity["urn"],
                "type": entity.get("type"),
                "name": entity.get("name"),
                "degree": item.get("degree"),
                "lineage_columns": item.get("lineageColumns", []),
            }
        )
    return entities


def _entity_summaries(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return []
    summaries = []
    for entity in payload:
        if not isinstance(entity, dict) or not isinstance(entity.get("urn"), str):
            continue
        summaries.append(
            {
                "urn": entity["urn"],
                "type": entity.get("type"),
                "name": entity.get("name"),
                "platform": _platform_name(entity.get("platform")),
                "owners": _owner_names(entity.get("ownership")),
                "description": entity.get("description"),
            }
        )
    return summaries


def _platform_name(platform: Any) -> str | None:
    if isinstance(platform, str):
        return platform
    if isinstance(platform, dict):
        value = platform.get("name") or platform.get("urn")
        return value if isinstance(value, str) else None
    return None


def _owner_names(ownership: Any) -> list[str]:
    if not isinstance(ownership, dict):
        return []
    owners = ownership.get("owners") or []
    names = []
    for owner in owners:
        if not isinstance(owner, dict):
            continue
        owner_entity = owner.get("owner")
        if isinstance(owner_entity, dict):
            editable = owner_entity.get("editableProperties") or {}
            properties = owner_entity.get("properties") or {}
            info = owner_entity.get("info") or {}
            name = (
                editable.get("displayName")
                or properties.get("displayName")
                or info.get("displayName")
                or owner_entity.get("name")
                or owner_entity.get("urn")
            )
        else:
            name = owner_entity or owner.get("urn") or owner.get("name")
        if isinstance(name, str):
            names.append(name)
    return names


def _asset_urns(context: dict[str, Any]) -> list[str]:
    urns: set[str] = set()
    for payload in (context.get("model"), context.get("related_entities")):
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("urn"), str):
                urns.add(item["urn"])
    for direction in ("upstream", "downstream"):
        urns.update(entity["urn"] for entity in _lineage_entities(context.get(direction)))
    return sorted(urns)


def _as_markdown(report: dict[str, Any]) -> str:
    model = report["model"]
    lines = [
        f"# {report['summary']}",
        "",
        f"- Model: `{model['name']}`",
        f"- Version: `{model['version']}`",
        f"- DataHub model: `{model['urn']}`",
        f"- Status: `{report['status']}`",
        "",
        "## Recommended action",
        "",
        report["recommended_action"],
        "",
    ]
    recovery = report.get("recovery")
    if isinstance(recovery, dict):
        lines.extend(
            [
                "## Recovery evidence",
                "",
                f"- Status: `{recovery.get('status', 'unknown')}`",
            ]
        )
        if recovery.get("verified_at") is not None:
            lines.append(f"- Verified at: `{recovery['verified_at']}`")
        checks = recovery.get("checks")
        if isinstance(checks, list):
            for check in checks:
                if not isinstance(check, dict):
                    continue
                lines.append(
                    f"- Check `{check.get('name', 'unnamed')}`: "
                    f"`{'passed' if check.get('passed') is True else 'failed'}`"
                )
                details = check.get("details")
                if isinstance(details, dict) and details:
                    lines.append(
                        f"  - Details: `{json.dumps(details, sort_keys=True, default=str)}`"
                    )
        lines.append("")
    lines.extend(["## Hypotheses", ""])
    for hypothesis in report["hypotheses"]:
        lines.append(
            f"- **{hypothesis['id']}** ({hypothesis['status']}): {hypothesis['statement']}"
        )
        if hypothesis["evidence_urns"]:
            lines.append(
                "  - Evidence: " + ", ".join(f"`{urn}`" for urn in hypothesis["evidence_urns"])
            )
    return "\n".join(lines)
