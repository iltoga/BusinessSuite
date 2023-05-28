# Use an official Python runtime as a parent image
FROM python:3

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV DJANGO_SETTINGS_MODULE RevisBaliCRM.settings.prod
ENV PATH="/home/revisbali/.local/bin:${PATH}"

# Set work directory
WORKDIR /usr/src/app

# Create a new user 'revisbali' with UID 1000 and GID 1000
RUN addgroup --gid 1000 revisbali && adduser --uid 1000 --ingroup revisbali --home /home/revisbali --shell /bin/sh --disabled-password --gecos "" revisbali

# Change to non-root privilege
USER revisbali

# Install dependencies
COPY --chown=revisbali:revisbali requirements.txt ./
RUN python3 -m pip install --upgrade pip
RUN pip install --no-warn-script-location --no-cache-dir -r requirements.txt

# Copy start script into the Docker image
COPY --chown=revisbali:revisbali start.sh /usr/src/app/

CMD ["/bin/bash", "/usr/src/app/start.sh"]

EXPOSE 8000
