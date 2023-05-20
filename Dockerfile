# Use an official Python runtime as a parent image
FROM python:3

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV DJANGO_SETTINGS_MODULE RevisBaliCRM.settings.prod

# Set work directory
WORKDIR /usr/src/app

# Create and activate the virtual environment
RUN python3 -m venv venv
RUN /bin/bash -c "source venv/bin/activate"

# Install dependencies
COPY requirements.txt ./
RUN venv/bin/pip install --no-cache-dir -r requirements.txt

# Copy project (STEF we use mount volume in the composer file instead)
# COPY . .

# Collect static files (STEF not working unless we copy the project)
# RUN python manage.py collectstatic --noinput

# Run Gunicorn
CMD ["venv/bin/gunicorn", "RevisBaliCRM.wsgi:application", "--bind", "0.0.0.0:8000", "--log-file", "-"]

EXPOSE 8000
