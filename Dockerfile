# ----------- Builder Stage -----------
FROM python:3.13 AS builder

# Set environment variables for build
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV DJANGO_SETTINGS_MODULE business_suite.settings.prod

# Install build dependencies
RUN apt-get update \
  && apt-get -y install --no-install-recommends \
  tesseract-ocr \
  poppler-utils \
  postgresql-client \
  curl \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

# Install uv using the installer script
ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh
ENV PATH="/root/.local/bin:$PATH"

# Copy only dependency files first for better cache
COPY pyproject.toml ./

# Install Python dependencies in editable mode
RUN uv pip install --system --editable . -vv --index-url https://pypi.org/simple

# Copy the rest of the source code (as root, for speed)
COPY . /usr/src/app/

# ----------- Final Stage -----------
FROM python:3.13 AS final

# Set environment variables for runtime
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV DJANGO_SETTINGS_MODULE business_suite.settings.prod
ENV PATH="/home/appuser/.local/bin:${PATH}"

# Install runtime dependencies only (no build tools)
RUN apt-get update \
  && apt-get -y install --no-install-recommends \
  tesseract-ocr \
  poppler-utils \
  postgresql-client \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

# Create a new user 'appuser' with UID 1000 and GID 1000
RUN addgroup --gid 1000 appuser && adduser --uid 1000 --ingroup appuser --home /home/appuser --shell /bin/sh --disabled-password --gecos "" appuser

# Create /usr/src/app directory and set permissions
RUN mkdir -p /usr/src/app && chown -R appuser:appuser /usr/src/app

# Set work directory
WORKDIR /usr/src/app

# Copy installed site-packages and app code from builder
COPY --from=builder /usr/src/app /usr/src/app
COPY --from=builder /root/.local /home/appuser/.local

# Change to non-root privilege
USER appuser

# Ensure scripts are executable at runtime
CMD /bin/bash -c "chmod +x /usr/src/app/scripts/* && /usr/src/app/start.sh"

EXPOSE 8000
