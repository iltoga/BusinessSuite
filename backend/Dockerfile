# -------- Base Stage --------
FROM python:3.14-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_PROJECT_ENVIRONMENT=/opt/venv

# Pin uv to avoid deploy-time behavior drift from `latest`.
COPY --from=ghcr.io/astral-sh/uv:0.9.25 /uv /uvx /bin/

WORKDIR /usr/src/app

RUN apt-get update && apt-get install -y --no-install-recommends \
  build-essential \
  libpq-dev \
  cron \
  curl \
  jq \
  procps \
  vim \
  && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./

RUN uv venv /opt/venv
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev


# -------- Web Runtime --------
FROM python:3.14-slim AS web

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=business_suite.settings.prod
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
  tesseract-ocr \
  poppler-utils \
  postgresql-client \
  libreoffice-writer-nogui \
  gettext \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src/app

COPY --from=base /opt/venv /opt/venv
COPY --from=base /usr/src/app /usr/src/app

RUN addgroup --gid 1000 appuser && \
  adduser --uid 1000 --ingroup appuser --home /home/appuser --shell /bin/sh --disabled-password --gecos "" appuser

USER appuser

CMD /bin/bash -c "chmod +x /usr/src/app/scripts/* && /usr/src/app/start.sh"

EXPOSE 8000
