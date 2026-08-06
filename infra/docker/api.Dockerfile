FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml ./
COPY alembic.ini ./
COPY src ./src

RUN python -m pip install --no-cache-dir .

RUN groupadd --system histograph && useradd --system --gid histograph --home-dir /nonexistent histograph

USER histograph

EXPOSE 8000

CMD ["uvicorn", "histograph.api.main:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8000"]
