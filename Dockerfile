# Use an official Python runtime as a parent image
FROM python:3

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV DJANGO_SETTINGS_MODULE business_suite.settings.prod
ENV PATH="/home/appuser/.local/bin:${PATH}"

# Create a new user 'appuser' with UID 1000 and GID 1000
RUN addgroup --gid 1000 appuser && adduser --uid 1000 --ingroup appuser --home /home/appuser --shell /bin/sh --disabled-password --gecos "" appuser

# Create /usr/src/app directory and change ownership to appuser
# It will be shadowed by volume, but it's necessary to create the directory otherwise it will be created with root ownership
RUN mkdir -p /usr/src/app && chown -R appuser:appuser /usr/src/app

# Set work directory
WORKDIR /usr/src/app

ENV PYHTONUNBUFFERED=1

# Install Tesseract and its language packs
RUN apt-get update \
  && apt-get -y install \
  && apt-get -y install tesseract-ocr \
  && apt-get -y install poppler-utils \
  && apt-get -y install postgresql-client \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

# Install uv using the installer script and add to PATH
ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh
ENV PATH="/root/.local/bin:$PATH"

# Copy pyproject.toml and install dependencies as root before switching user
COPY pyproject.toml ./
RUN uv pip install --system --editable .

# Change to non-root privilege
USER appuser

# Copy project
COPY --chown=appuser:appuser . /usr/src/app/

# Copy start script into the Docker image and make it executable
# COPY --chown=appuser:appuser scripts/start.sh /usr/src/app/
# RUN chmod +x /usr/src/app/start.sh

CMD /bin/bash -c "chmod +x /usr/src/app/scripts/* && /usr/src/app/start.sh"

EXPOSE 8000
