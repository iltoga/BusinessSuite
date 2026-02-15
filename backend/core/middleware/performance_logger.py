import logging
import time

from django.conf import settings
from django.db import connection

from core.services.logger_service import Logger

logger = Logger.get_logger("performance")


class PerformanceLoggingMiddleware:
    """
    Logs detailed timing info for each HTTP request to detect slow or hanging endpoints.
    Works in both sync and async Django views.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.slow_request_warning_ms = float(getattr(settings, "SLOW_REQUEST_WARNING_MS", 1000))

    def __call__(self, request):
        start_time = time.perf_counter()
        num_queries_before = len(connection.queries)

        response = self.get_response(request)

        duration = (time.perf_counter() - start_time) * 1000  # ms
        num_queries_after = len(connection.queries)
        num_queries = num_queries_after - num_queries_before

        logger.info(
            f"{request.method} {request.path} | "
            f"Status: {response.status_code} | "
            f"Time: {duration:.2f} ms | "
            f"Queries: {num_queries}"
        )

        if duration > self.slow_request_warning_ms:
            logger.warning(f"SLOW REQUEST: {request.method} {request.path} took {duration:.2f} ms")

        return response

    async def __acall__(self, request):
        start_time = time.perf_counter()
        num_queries_before = len(connection.queries)

        response = await self.get_response(request)

        duration = (time.perf_counter() - start_time) * 1000
        num_queries_after = len(connection.queries)
        num_queries = num_queries_after - num_queries_before

        logger.info(
            f"{request.method} {request.path} | "
            f"Status: {response.status_code} | "
            f"Time: {duration:.2f} ms | "
            f"Queries: {num_queries}"
        )

        if duration > self.slow_request_warning_ms:
            logger.warning(f"SLOW ASYNC REQUEST: {request.method} {request.path} took {duration:.2f} ms")

        return response
