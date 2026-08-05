FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
COPY packages ./packages
COPY server ./server

RUN python -m pip install --no-cache-dir '.[postgres]'

EXPOSE 8000

CMD ["uvicorn", "histograph_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
