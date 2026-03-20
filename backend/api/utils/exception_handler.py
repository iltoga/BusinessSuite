from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.views import exception_handler

from api.utils.contracts import build_error_payload


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        request = context.get("request") if isinstance(context, dict) else None

        if isinstance(exc, ValidationError):
            response.data = build_error_payload(
                code=getattr(exc, "default_code", "validation_error"),
                message="Validation error",
                details=response.data,
                request=request,
            )
            return response

        if isinstance(exc, NotFound):
            response.data = build_error_payload(
                code=getattr(exc, "default_code", "not_found"),
                message="Not found",
                details=getattr(exc, "detail", None) or response.data,
                request=request,
            )
            return response

        detail = None
        code = getattr(exc, "default_code", "error")
        if isinstance(response.data, dict) and "detail" in response.data:
            detail = response.data.get("detail")
        else:
            detail = response.data

        response.data = build_error_payload(
            code=code,
            message=str(detail or "Error"),
            details=detail if detail is not None and detail != str(detail or "") else None,
            request=request,
        )

    return response
