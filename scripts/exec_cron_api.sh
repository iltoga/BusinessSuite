#!/bin/bash

#
# This script is copied to the container, together with the .env file and executed by the cron job.
#

echo "Cron api started at $(date)"

# Load environment variables from .env file
if [ -f .env ]
then
  export $(cat .env | sed 's/#.*//g' | xargs)
fi

# Check if SYSTEM_USER_PASSWORD and SYSTEM_USER_EMAIL are set and not empty
if [[ -z "${SYSTEM_USER_PASSWORD}" ]]; then
  echo "Error: SYSTEM_USER_PASSWORD is not set or empty. Please set the SYSTEM_USER_PASSWORD environment variable."
  exit 1
fi
if [[ -z "${SYSTEM_USER_EMAIL}" ]]; then
  echo "Error: SYSTEM_USER_EMAIL is not set or empty. Please set the SYSTEM_USER_EMAIL environment variable."
  exit 1
fi

HOSTADDR="revisbali-crm"
BIN_DIR="/usr/bin"

# Add Curl command to obtain the access token from revisbali-crm container
# using a GET request
TOKEN=$($BIN_DIR/curl -v -X POST -F "username=system" -F "password=${SYSTEM_USER_PASSWORD}" $HOSTADDR:8000/api/api-token-auth/ | $BIN_DIR/jq -r '.token')

# Add Curl command to execute the API call to the endpoint
RESPONSE=$($BIN_DIR/curl -s -H "Authorization: Bearer ${TOKEN}" -X GET $HOSTADDR:8000/api/cron/exec_cron_jobs/)

# Optional: Print the response
echo "${RESPONSE}"
echo "Cron api executed at $(date)"