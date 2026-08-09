import asyncio
import hmac
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Request, status

from demo.runtime.service import ReferenceRuntime
from demo.runtime.settings import ReferenceRuntimeSettings
from demo.runtime.state import RuntimeStateStore
from demo.runtime.telemetry import HistographTelemetrySink, TelemetrySink, TelemetryWorker
from demo.runtime.types import (
    ApplyManifestRequest,
    ComparisonResponse,
    OutcomeBatchRequest,
    PredictionBatchRequest,
    PredictionBatchResponse,
    PredictionRequest,
    PredictionResponse,
    RuntimeStateView,
)


def create_runtime_app(
    settings: ReferenceRuntimeSettings | None = None,
    *,
    telemetry_sink: TelemetrySink | None = None,
) -> FastAPI:
    configured = settings or ReferenceRuntimeSettings()
    state = RuntimeStateStore(configured.state_path)
    runtime = ReferenceRuntime(configured.workspace_root, state)
    telemetry = TelemetryWorker(
        state,
        telemetry_sink or HistographTelemetrySink(configured.histograph_api_url),
        batch_size=configured.telemetry_batch_size,
        retry_seconds=configured.telemetry_retry_seconds,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(telemetry.run_forever(configured.telemetry_poll_seconds))
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            state.close()

    app = FastAPI(title="Histograph reference runtime", lifespan=lifespan)
    app.state.settings = configured
    app.state.runtime = runtime
    app.state.runtime_state = state
    app.state.telemetry_worker = telemetry

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/runtime", response_model=RuntimeStateView)
    def runtime_state(request: Request) -> RuntimeStateView:
        return request.app.state.runtime.view()

    @app.post("/v1/deployments/apply")
    def apply_manifest(
        event: ApplyManifestRequest,
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        _authorize(authorization, request.app.state.settings.control_token)
        try:
            return request.app.state.runtime.apply(event.revision, event.content)
        except (FileNotFoundError, RuntimeError, ValueError) as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
            ) from error

    @app.post("/v1/predict", response_model=PredictionResponse)
    def predict(event: PredictionRequest, request: Request) -> PredictionResponse:
        try:
            return request.app.state.runtime.predict(event)
        except RuntimeError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
            ) from error

    @app.post("/v1/predict/batch", response_model=PredictionBatchResponse)
    def predict_batch(batch: PredictionBatchRequest, request: Request) -> PredictionBatchResponse:
        try:
            return PredictionBatchResponse(
                events=request.app.state.runtime.predict_many(batch.events)
            )
        except RuntimeError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
            ) from error

    @app.post("/v1/compare", response_model=ComparisonResponse)
    def compare(
        event: PredictionRequest,
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
    ) -> ComparisonResponse:
        _authorize(authorization, request.app.state.settings.control_token)
        try:
            return request.app.state.runtime.compare(event)
        except RuntimeError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
            ) from error

    @app.post("/v1/outcomes/batch", status_code=status.HTTP_202_ACCEPTED)
    def outcomes(batch: OutcomeBatchRequest, request: Request) -> dict[str, int]:
        request.app.state.runtime.record_outcomes(batch.events)
        return {"accepted": len(batch.events)}

    return app


def _authorize(authorization: str | None, expected_token: str | None) -> None:
    if expected_token is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Reference runtime control token is not configured",
        )
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(token, expected_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid reference runtime control token",
        )
