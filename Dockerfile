# syntax=docker/dockerfile:1

# --- Stage 1: Base system dependencies ---
FROM python:3.13-slim as base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=business_suite.settings.prod
ENV PATH="/home/appuser/.local/bin:${PATH}"

RUN apt-get update \
  && apt-get -y install --no-install-recommends \
  tesseract-ocr \
  poppler-utils \
  postgresql-client \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

# Create a new user 'appuser'
RUN addgroup --gid 1000 appuser && adduser --uid 1000 --ingroup appuser --home /home/appuser --shell /bin/sh --disabled-password --gecos "" appuser

WORKDIR /usr/src/app

# --- Stage 2: Python dependencies ---
FROM base as builder

COPY pyproject.toml ./
# Install uv using the installer script and add to PATH
ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh \
  && uv pip install --system --editable .

# --- Stage 3: Production image ---
FROM base

WORKDIR /usr/src/app

# Copy installed Python packages from builder
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /root/.local /root/.local

# Copy project files as non-root user
COPY --chown=appuser:appuser . /usr/src/app/

USER appuser

CMD /bin/bash -c "chmod +x /usr/src/app/scripts/* && /usr/src/app/start.sh"

EXPOSE 8000