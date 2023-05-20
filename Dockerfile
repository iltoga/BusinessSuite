# Use an official Python runtime as a parent image
FROM python:3

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV DJANGO_SETTINGS_MODULE RevisBaliCRM.settings.prod

# Set work directory
WORKDIR /usr/src/app

# Create the virtual environment
RUN python3 -m venv venv

# Install dependencies
COPY requirements.txt ./
RUN /usr/src/app/venv/bin/pip install --upgrade pip
RUN /usr/src/app/venv/bin/pip install --no-cache-dir -r requirements.txt
RUN /usr/src/app/venv/bin/pip install gunicorn

# Run Gunicorn
CMD ["/usr/src/app/venv/bin/gunicorn", "RevisBaliCRM.wsgi:application", "--bind", "0.0.0.0:8000", "--log-file", "-"]

EXPOSE 8000
