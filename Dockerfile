FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH=/app/.venv/bin:$PATH \
    PYTHONPATH=/app/server/src:/app

WORKDIR /app

RUN pip install --no-cache-dir uv==0.12.3

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --extra demo --no-install-project

COPY server ./server
COPY demo ./demo
COPY .histograph ./.histograph
COPY README.md LICENSE THIRD_PARTY_NOTICES.md ./

RUN test -f demo/artifacts/mobile_money_fraud.joblib \
    && test -f demo/artifacts/model_manifest.json \
    && test -f demo/artifacts/replay.parquet

EXPOSE 8000
CMD ["uvicorn", "histograph.api.main:app", "--app-dir", "server/src", "--host", "0.0.0.0", "--port", "8000"]
