# syntax=docker/dockerfile:1

FROM python:3.13-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /srv/app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt ./
RUN pip install -r requirements.txt

FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN useradd --create-home --uid 10001 appuser
WORKDIR /srv/app

# Writable home for runtime state, currently the generated JWT signing key.
# Docker seeds a fresh named volume from this directory, including its owner -
# without the chown the mounted volume would be root-owned and the non-root
# process could not write to it.
RUN mkdir -p /var/lib/tasktracker && chown appuser:appuser /var/lib/tasktracker

COPY --from=builder /opt/venv /opt/venv
COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser alembic.ini pyproject.toml ./
COPY --chown=appuser:appuser alembic ./alembic

USER appuser

EXPOSE 8000

# Migrations run as a separate, explicit step (see Makefile / README):
#   docker compose exec app alembic upgrade head
# The service itself never migrates on startup.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]