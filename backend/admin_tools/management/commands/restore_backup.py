"""
FILE_ROLE: Management command for the admin tools app backup restore workflow.

KEY_COMPONENTS:
- Command: Django management command entrypoint.

INTERACTIONS:
- Depends on: admin_tools.services and Django management command machinery.

AI_GUIDELINES:
- Keep command orchestration thin and delegate the restore workflow to services.
- Preserve command arguments and output contract because scripts and tests depend on them.
"""

from pathlib import Path

from admin_tools import services
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Restore database and media from a backup archive file."

    def add_arguments(self, parser):
        parser.add_argument(
            "backup_file",
            help="Backup file path or filename in BACKUPS_ROOT (e.g. backup-20260218-120000.tar.zst).",
        )
        parser.add_argument(
            "--include-users",
            action="store_true",
            help="Request full restore including auth/user-related data (auto-detected from fixture content).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Skip interactive confirmation prompt.",
        )

    def _resolve_backup_path(self, backup_file: str) -> Path:
        candidate = Path(backup_file).expanduser()
        if candidate.is_absolute():
            return candidate

        cwd_candidate = Path.cwd() / candidate
        if cwd_candidate.exists():
            return cwd_candidate

        backups_candidate = Path(services.BACKUPS_DIR) / candidate
        return backups_candidate

    def handle(self, *args, **options):
        backup_file = str(options["backup_file"]).strip()
        include_users = bool(options.get("include_users"))
        force = bool(options.get("force"))

        if not backup_file:
            raise CommandError("backup_file cannot be empty.")

        backup_path = self._resolve_backup_path(backup_file)
        if not backup_path.exists():
            raise CommandError(f"Backup file not found: {backup_path}")
        if not backup_path.is_file():
            raise CommandError(f"Backup path is not a file: {backup_path}")

        if not force:
            answer = input(
                f"About to restore from '{backup_path}'. This will modify database data. Continue? [y/N]: "
            ).strip()
            if answer.lower() not in {"y", "yes"}:
                raise CommandError("Restore aborted by user.")

        self.stdout.write(f"Starting restore from: {backup_path}")
        if include_users:
            self.stdout.write("include_users=True requested.")

        try:
            for message in services.restore_from_file(str(backup_path), include_users=include_users):
                self.stdout.write(str(message))
        except Exception as exc:
            raise CommandError(f"Restore failed: {exc}") from exc

        self.stdout.write(self.style.SUCCESS("Restore completed."))
