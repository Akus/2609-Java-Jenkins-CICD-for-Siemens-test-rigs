# ---- base -------------------------------------------------------------------
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml ./
COPY rig_api ./rig_api
COPY alembic.ini ./
COPY alembic ./alembic

# ---- test: `docker build --target test .` or `make test` --------------------
FROM base AS test
RUN pip install -e ".[dev]"
COPY tests ./tests
RUN ruff check rig_api tests && pytest -q

# ---- runtime ----------------------------------------------------------------
FROM base AS runtime
RUN pip install . \
 && useradd --system --uid 10001 --create-home rigapi \
 && mkdir -p /data && chown rigapi:rigapi /data
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
USER rigapi
EXPOSE 8000
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "rig_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
