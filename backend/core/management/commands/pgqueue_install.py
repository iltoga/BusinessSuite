from __future__ import annotations

import asyncio

from core.services.logger_service import Logger
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

logger = Logger.get_logger(__name__)


def _database_connect_kwargs() -> dict[str, str]:
    database = settings.DATABASES.get("default", {})
    return {
        "dbname": str(database.get("NAME") or ""),
        "user": str(database.get("USER") or ""),
        "password": str(database.get("PASSWORD") or ""),
        "host": str(database.get("HOST") or ""),
        "port": str(database.get("PORT") or ""),
    }


class Command(BaseCommand):
    help = "Install/upgrade PgQueuer database objects."

    def handle(self, *args, **options):
        try:
            asyncio.run(self._install())
        except Exception as exc:
            raise CommandError(f"PgQueuer schema install failed: {exc}") from exc

        self.stdout.write(self.style.SUCCESS("PgQueuer database objects are ready."))

    async def _install(self) -> None:
        try:
            import psycopg
            from pgqueuer.queries import Queries
        except Exception as exc:
            raise RuntimeError("Missing pgqueuer runtime dependencies (psycopg).") from exc

        connect_kwargs = _database_connect_kwargs()
        connection = await psycopg.AsyncConnection.connect(**connect_kwargs, autocommit=True)
        try:
            queries = Queries.from_psycopg_connection(connection)
            await queries.install()
            await queries.upgrade()
            logger.info("PgQueuer install/upgrade completed")
        finally:
            await connection.close()
