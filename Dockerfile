# Use an official Python runtime as a parent image
FROM python:3

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV DJANGO_SETTINGS_MODULE RevisBaliCRM.settings.prod
ENV PATH="/home/revisbali/.local/bin:${PATH}"

# Create a new user 'revisbali' with UID 1000 and GID 1000
RUN addgroup --gid 1000 revisbali && adduser --uid 1000 --ingroup revisbali --home /home/revisbali --shell /bin/sh --disabled-password --gecos "" revisbali

# Create /usr/src/app directory and change ownership to revisbali
# It will be shadowed by volume, but it's necessary to create the directory otherwise it will be created with root ownership
RUN mkdir -p /usr/src/app && chown -R revisbali:revisbali /usr/src/app

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

# Change to non-root privilege
USER revisbali

# Install dependencies
COPY --chown=revisbali:revisbali requirements.txt ./
RUN python3 -m pip install --upgrade pip
RUN pip install --no-warn-script-location --no-cache-dir -r requirements.txt

# Copy project
COPY --chown=revisbali:revisbali . /usr/src/app/

# Copy start script into the Docker image and make it executable
# COPY --chown=revisbali:revisbali scripts/start.sh /usr/src/app/
# RUN chmod +x /usr/src/app/start.sh

CMD /bin/bash -c "chmod +x /usr/src/app/scripts/* && /usr/src/app/start.sh"

EXPOSE 8000
