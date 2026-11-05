FROM python:3.13-slim-bookworm@sha256:281d39ff02e3b389401586134ff9e6572954687822a58055ec07a60ded4e0b7f
COPY --from=tools /uv /usr/local/bin/uv
COPY --from=tools /docker /usr/local/bin/docker
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy PYTHONDONTWRITEBYTECODE=1 \
    PATH=/app/backend/.venv/bin:$PATH OPENHANDS_SUPPRESS_BANNER=1 \
    LITELLM_LOCAL_MODEL_COST_MAP=True
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
COPY backend/src ./src
RUN --mount=type=bind,from=uvcache,target=/root/.cache/uv,rw \
    uv sync --locked --offline --extra worker --no-dev --python /usr/local/bin/python \
    && docker --version
COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
COPY deploy/ops /app/ops
USER 10001:10001
ENTRYPOINT ["python", "/app/ops/launch.py"]
