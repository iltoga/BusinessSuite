#!/bin/bash

# Run as root
touch /logs/cron.log
cron

# Switch to revisbali user and run the rest of commands
su - revisbali -c "/usr/src/app/start.sh && tail -f /logs/cron.log"