import logging
import time

from django.conf import settings
from django.db import connection

from core.services.logger_service import Logger
from core.telemetry.otlp_exporter import current_unix_nano, trace_exporter

logger = Logger.get_logger("performance")


class PerformanceLoggingMiddleware:
    """
    Logs detailed timing info for each HTTP request to detect slow or hanging endpoints.
    Works in both sync and async Django views.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        self.slow_request_warning_ms = float(getattr(settings, "SLOW_REQUEST_WARNING_MS", 1000))
        self.trace_exporter = trace_exporter

    def __call__(self, request):
        start_time = time.perf_counter()
        start_unix_nano = current_unix_nano()
        num_queries_before = len(connection.queries)
        request_path = request.path or "/"
        request_query = request.META.get("QUERY_STRING", "")
        request_host = request.get_host() if hasattr(request, "get_host") else ""
        user_agent = request.META.get("HTTP_USER_AGENT", "")

        span_context = self.trace_exporter.start_server_span(request.headers.get("traceparent"))

        try:
            response = self.get_response(request)
        except Exception as exc:
            duration = (time.perf_counter() - start_time) * 1000  # ms
            num_queries_after = len(connection.queries)
            num_queries = num_queries_after - num_queries_before
            self._export_trace_span(
                request=request,
                span_context=span_context,
                request_path=request_path,
                request_query=request_query,
                request_host=request_host,
                user_agent=user_agent,
                status_code=500,
                duration_ms=duration,
                num_queries=num_queries,
                start_unix_nano=start_unix_nano,
                error_type=exc.__class__.__name__,
                error_message=str(exc),
            )
            raise

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

        self._export_trace_span(
            request=request,
            span_context=span_context,
            request_path=request_path,
            request_query=request_query,
            request_host=request_host,
            user_agent=user_agent,
            status_code=response.status_code,
            duration_ms=duration,
            num_queries=num_queries,
            start_unix_nano=start_unix_nano,
        )

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

    def _export_trace_span(
        self,
        *,
        request,
        span_context,
        request_path: str,
        request_query: str,
        request_host: str,
        user_agent: str,
        status_code: int,
        duration_ms: float,
        num_queries: int,
        start_unix_nano: str,
        error_type: str = "",
        error_message: str = "",
    ) -> None:
        span_name = f"{request.method} {request_path}"
        attributes = {
            "http.request.method": request.method,
            "http.response.status_code": status_code,
            "url.path": request_path,
            "url.query": request_query,
            "server.address": request_host,
            "http.route": request.resolver_match.route if request.resolver_match else request_path,
            "user_agent.original": user_agent,
            "db.sql.query_count": num_queries,
            "request.duration.ms": round(duration_ms, 2),
        }
        if error_type:
            attributes["error.type"] = error_type
        if error_message:
            attributes["error.message"] = error_message[:500]

        self.trace_exporter.export_http_server_span(
            span_context=span_context,
            span_name=span_name,
            start_time_unix_nano=start_unix_nano,
            end_time_unix_nano=current_unix_nano(),
            attributes=attributes,
            status_code=status_code,
        )
