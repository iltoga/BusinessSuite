# ----------- Builder Stage -----------
FROM python:3.14-slim AS builder

# Set environment variables for build
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Install uv using the official binary
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set work directory
WORKDIR /usr/src/app

# Install build dependencies for C-extensions (if needed by psycopg2, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
  build-essential \
  libpq-dev \
  && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy only dependency files for caching
COPY pyproject.toml uv.lock ./

# Install dependencies into a virtual environment
# We use --no-dev to exclude testing tools and --frozen to respect the lockfile
RUN uv sync --frozen --no-dev --no-install-project

# Compile requirements.txt using uv (for compatibility with other tools that still use requirements.txt)
RUN uv pip compile pyproject.toml > requirements.txt

# Install dependencies from requirements.txt (system-wide): leave commented for reference
# RUN uv pip install --system -r requirements.txt

# Copy the source code
COPY . .

# Install the project itself
RUN uv sync --frozen --no-dev

# ----------- Final Stage -----------
FROM python:3.14-slim AS final

# Set environment variables for runtime
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=business_suite.settings.prod
ENV PATH="/usr/src/app/.venv/bin:$PATH"

# Install runtime dependencies
RUN apt-get update \
  && apt-get -y install --no-install-recommends \
  tesseract-ocr \
  poppler-utils \
  postgresql-client \
  libreoffice-writer-nogui \
  gettext \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN addgroup --gid 1000 appuser && \
  adduser --uid 1000 --ingroup appuser --home /home/appuser --shell /bin/sh --disabled-password --gecos "" appuser

# Set work directory
WORKDIR /usr/src/app

# Copy the virtual environment and application code from builder
# Copying the .venv is cleaner than hardcoding python3.14/site-packages paths
COPY --from=builder --chown=appuser:appuser /usr/src/app /usr/src/app

# Change to non-root privilege
USER appuser

# Ensure scripts are executable and start the application
CMD /bin/bash -c "chmod +x /usr/src/app/scripts/* && /usr/src/app/start.sh"

EXPOSE 8000