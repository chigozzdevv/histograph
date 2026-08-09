from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status

from histograph.monitors.types import Monitor

router = APIRouter(prefix="/v1/monitors", tags=["monitors"])


@router.get("")
def list_monitors(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, object]]:
    return request.app.state.monitors.list_all(limit)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_monitor(monitor: Monitor, request: Request) -> dict[str, object]:
    if request.app.state.models.get(monitor.model) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Register the model before creating a monitor",
        )
    monitor_id = request.app.state.monitors.save(monitor)
    return {"id": monitor_id, "monitor": monitor.model_dump(mode="json")}


@router.get("/{monitor_id}")
def get_monitor(monitor_id: UUID, request: Request) -> dict[str, object]:
    monitor = request.app.state.monitors.get(monitor_id)
    if monitor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found")
    return monitor


@router.get("/{monitor_id}/runs")
def list_monitor_runs(
    monitor_id: UUID,
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict[str, object]]:
    if request.app.state.monitors.get(monitor_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found")
    return request.app.state.monitors.runs(monitor_id, limit)
