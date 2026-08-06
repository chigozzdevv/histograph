FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src

RUN python -m pip install --no-cache-dir .

RUN groupadd --system histograph && useradd --system --gid histograph --home-dir /nonexistent histograph

USER histograph

CMD ["python", "-m", "histograph.worker.main"]
