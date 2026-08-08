from typing import Any, Protocol
from uuid import UUID


class InvestigationControl(Protocol):
    def get_incident(self, incident_id: UUID) -> dict[str, Any] | None: ...

    def update_incident(
        self, incident_id: UUID, summary: str, evidence: dict[str, Any]
    ) -> bool: ...


class InvestigationDataHub(Protocol):
    async def collect_context(self, model_urn: str, max_hops: int) -> dict[str, Any]: ...

    async def save_investigation(
        self, title: str, content: str, related_assets: list[str]
    ) -> dict[str, Any]: ...


class InvestigationAgent:
    def __init__(self, control: InvestigationControl, datahub: InvestigationDataHub):
        self._control = control
        self._datahub = datahub

    async def investigate(
        self,
        incident_id: UUID,
        model_urn: str,
        max_hops: int = 3,
        write_back: bool = False,
    ) -> dict[str, Any]:
        incident = self._control.get_incident(incident_id)
        if incident is None:
            raise LookupError("Incident not found")

        context = await self._datahub.collect_context(model_urn, max_hops=max_hops)
        report = _build_report(incident, model_urn, context)
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
        self._control.update_incident(incident_id, report["summary"], evidence)
        return {"incident_id": incident_id, **report, "writeback": writeback}


def _build_report(
    incident: dict[str, Any], model_urn: str, context: dict[str, Any]
) -> dict[str, Any]:
    upstream = _lineage_entities(context.get("upstream"))
    downstream = _lineage_entities(context.get("downstream"))
    related = _entity_summaries(context.get("related_entities"))
    detection = (incident.get("evidence") or {}).get("detection", {})
    metric = incident.get("metric", "signal")
    model = incident.get("model", "model")
    version = incident.get("version", "unknown")

    if not upstream and not downstream:
        status = "inconclusive"
        summary = (
            f"DataHub returned no lineage for {model} {version}; Histograph cannot establish "
            "a dependency-level explanation or blast radius."
        )
    else:
        status = "lineage_mapped"
        summary = (
            f"Histograph mapped {len(upstream)} upstream dependencies and "
            f"{len(downstream)} downstream consumers for {model} {version}. "
            f"The {metric} signal is dependency-consistent, but DataHub lineage alone "
            "does not prove which asset changed."
        )

    return {
        "status": status,
        "summary": summary,
        "model": {"name": model, "version": version, "urn": model_urn},
        "trigger": {
            "signal": incident.get("signal"),
            "metric": metric,
            "detection": detection,
        },
        "hypotheses": [
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
        "evidence": {
            "datahub_model_urn": model_urn,
            "tools": context.get("tool_trace", []),
            "raw_context": context,
        },
        "recommended_action": (
            "Keep the incident open, inspect the candidate upstream assets, and only "
            "approve rollback or retraining after a change or quality signal is corroborated."
        ),
    }


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
        name = owner.get("owner") or owner.get("urn") or owner.get("name")
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
        "## Hypotheses",
        "",
    ]
    for hypothesis in report["hypotheses"]:
        lines.append(
            f"- **{hypothesis['id']}** ({hypothesis['status']}): {hypothesis['statement']}"
        )
        if hypothesis["evidence_urns"]:
            lines.append(
                "  - Evidence: "
                + ", ".join(f"`{urn}`" for urn in hypothesis["evidence_urns"])
            )
    return "\n".join(lines)
