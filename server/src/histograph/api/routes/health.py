from fastapi import APIRouter, HTTPException, Request, status

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def readiness(request: Request) -> dict[str, object]:
    checks: dict[str, str] = {}
    for name, store in (
        ("postgres", request.app.state.control),
        ("clickhouse", request.app.state.telemetry),
    ):
        try:
            store.ping()
            checks[name] = "ok"
        except Exception:
            checks[name] = "unavailable"

    if any(result != "ok" for result in checks.values()):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unavailable", "checks": checks},
        )
    return {"status": "ready", "checks": checks}
