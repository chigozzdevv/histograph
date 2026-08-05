import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, status
from histograph_domain import RunRequest
from histograph_domain.base import DomainModel
from histograph_runner import RunExecutionError
from pydantic import Field
from sqlalchemy import select

from histograph_api.database.models import RunRecord

router = APIRouter(prefix="/runs", tags=["runs"])


class RunResponse(DomainModel):
    id: str
    test_case_id: str
    test_case_name: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    error: str | None
    result: dict[str, Any] | None


class RunListResponse(DomainModel):
    items: list[RunResponse] = Field(default_factory=list)


@router.get("", response_model=RunListResponse)
async def list_runs(request: Request) -> RunListResponse:
    async with request.app.state.session_factory() as session:
        result = await session.scalars(select(RunRecord).order_by(RunRecord.started_at.desc()))
        records = result.all()
    return RunListResponse(items=[_to_response(record) for record in records])


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(run_id: str, request: Request) -> RunResponse:
    async with request.app.state.session_factory() as session:
        record = await session.get(RunRecord, run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return _to_response(record)


@router.post("", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
async def execute_run(body: RunRequest, request: Request) -> RunResponse:
    run_id = str(uuid4())
    started_at = datetime.now(UTC)
    record = RunRecord(
        id=run_id,
        test_case_id=body.test_case.id,
        test_case_name=body.test_case.name,
        status="executing",
        started_at=started_at,
        request_json=json.dumps(_redacted_request(body)),
    )
    async with request.app.state.session_factory() as session:
        session.add(record)
        await session.commit()
        try:
            result = await request.app.state.runner.execute(body, run_id=run_id)
            record.status = result.status.value
            record.completed_at = result.completed_at
            record.result_json = result.model_dump_json()
        except RunExecutionError as error:
            record.status = "error"
            record.completed_at = datetime.now(UTC)
            record.error = str(error)
        await session.commit()
        await session.refresh(record)
    return _to_response(record)


def _to_response(record: RunRecord) -> RunResponse:
    return RunResponse(
        id=record.id,
        test_case_id=record.test_case_id,
        test_case_name=record.test_case_name,
        status=record.status,
        started_at=record.started_at,
        completed_at=record.completed_at,
        error=record.error,
        result=json.loads(record.result_json) if record.result_json else None,
    )


def _redacted_request(request: RunRequest) -> dict[str, Any]:
    payload = request.model_dump(mode="json")
    payload["datahub"]["token"] = "[redacted]"
    if payload["agent"].get("token") is not None:
        payload["agent"]["token"] = "[redacted]"
    return payload
