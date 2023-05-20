# Use an official Python runtime as a parent image
FROM python:3

# Set environment varibles
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV DJANGO_SETTINGS_MODULE RevisBaliCRM.settings.prod

# Set work directory
WORKDIR /usr/src/app

# Install dependencies
COPY requirements.txt ./
RUN python3 -m pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy project (STEF we use mount volume in the composer file instead)
COPY . .

# Collect static files (STEF not working unless we copy the project)
RUN python manage.py collectstatic --noinput

# Run Gunicorn
CMD ["gunicorn", "RevisBaliCRM.wsgi:application", "--bind", "0.0.0.0:8000", "--log-file", "-"]

EXPOSE 8000