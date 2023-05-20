# Use an official Python runtime as a parent image
FROM python:3

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV DJANGO_SETTINGS_MODULE RevisBaliCRM.settings.prod

# Set work directory
WORKDIR /usr/src/app

# Install dependencies
COPY requirements.txt ./
RUN python3 -m pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy start script into the Docker image and make it executable
COPY start.sh /usr/src/app/
RUN chmod +x /usr/src/app/start.sh

CMD ["/usr/src/app/start.sh"]

EXPOSE 8000
