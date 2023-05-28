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
RUN mkdir -p /usr/src/app && chown -R revisbali:revisbali /usr/src/app

# Set work directory
WORKDIR /usr/src/app

# Change to non-root privilege
USER revisbali

# Install dependencies
COPY --chown=revisbali:revisbali requirements.txt ./
RUN python3 -m pip install --upgrade pip
RUN pip install --no-warn-script-location --no-cache-dir -r requirements.txt

# Copy project
COPY --chown=revisbali:revisbali . /usr/src/app/

# Copy start script into the Docker image and make it executable
COPY --chown=revisbali:revisbali start.sh /usr/src/app/
RUN chmod +x /usr/src/app/start.sh

CMD ["/bin/bash", "/usr/src/app/start.sh"]

EXPOSE 8000
