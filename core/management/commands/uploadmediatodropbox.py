import logging
import os

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand
from storages.backends.dropbox import DropBoxStorage

from core.utils.dropbox_refresh_token import refresh_dropbox_token

# file logger in prod and console in dev
logger = logging.getLogger("django")


class Command(BaseCommand):
    help = "Uploads a directory to Dropbox"

    def add_arguments(self, parser):
        parser.add_argument("dropbox_dir", type=str, help="The Dropbox directory to upload the files to")

    def handle(self, *args, **kwargs):
        # Initialize DropboxStorage with the options from DBBACKUP_STORAGE_OPTIONS
        ds = DropBoxStorage(
            oauth2_access_token=refresh_dropbox_token(
                os.getenv("DROPBOX_APP_KEY"),
                os.getenv("DROPBOX_APP_SECRET"),
                os.getenv("DROPBOX_OAUTH2_REFRESH_TOKEN"),
            ),
            app_key=os.getenv("DROPBOX_APP_KEY"),
            app_secret=os.getenv("DROPBOX_APP_SECRET"),
        )

        # Define the local directory
        local_directory = settings.MEDIA_ROOT

        # Get the Dropbox destination directory from the command line argument
        dropbox_destination_directory = kwargs["dropbox_dir"]
        # delete all files in the dropbox_destination_directory if it exists
        if ds.exists(dropbox_destination_directory):
            ds.delete(dropbox_destination_directory)

        # Iterate over files in the local directory
        for root, dirs, files in os.walk(local_directory):
            for file in files:
                # Construct full local file path
                local_file_path = os.path.join(root, file)

                # Construct destination file path in Dropbox
                relative_path = os.path.relpath(local_file_path, local_directory)
                dropbox_file_path = os.path.join(dropbox_destination_directory, relative_path)

                # Open the local file in binary mode
                with open(local_file_path, "rb") as f:
                    django_file = File(f)

                    # Save file to Dropbox
                    ds._save(dropbox_file_path, django_file)
                    logger.info(f"Uploaded {dropbox_file_path} to Dropbox")
        logger.info(f"Directory has been successfully uploaded to Dropbox")
