from fastapi import APIRouter, HTTPException, Request, status

from histograph.models.types import ModelDefinition

router = APIRouter(prefix="/v1/models", tags=["models"])


@router.put("/{model_name}")
def register_model(
    model_name: str,
    model: ModelDefinition,
    request: Request,
) -> dict[str, object]:
    if model.name != model_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Path model name must match body model name",
        )
    model_id = request.app.state.models.save(model)
    return {"id": model_id, "model": model.model_dump(mode="json")}


@router.get("/{model_name}")
def get_model(model_name: str, request: Request) -> dict[str, object]:
    model = request.app.state.models.get(model_name)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
    return model
