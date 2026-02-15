from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.plumbing import build_bearer_security_scheme_object
from rest_framework.views import APIView


class JwtOrMockAuthenticationScheme(OpenApiAuthenticationExtension):
    # target_class can be a dotted path
    target_class = "business_suite.authentication.JwtOrMockAuthentication"
    name = "jwtAuth"

    def get_security_definition(self, auto_schema):
        # build a standard bearer JWT security scheme
        return build_bearer_security_scheme_object(
            header_name="Authorization", token_prefix="Bearer", bearer_format="JWT"
        )


# Preprocessing hook: exclude APIView endpoints that don't declare a serializer
# This reduces noisy "unable to guess serializer" errors for read-only or custom views
# that don't fit DRF's automatic discovery patterns.


def preprocess_exclude_api_views_without_serializer(endpoints, **kwargs):
    from rest_framework.viewsets import GenericViewSet, ViewSet

    filtered = []
    for path, path_regex, method, callback in endpoints:
        try:
            view_cls = getattr(callback, "cls", None)
            if view_cls and issubclass(view_cls, APIView):
                # Always keep ViewSets as they are standard DRF discovery targets
                if issubclass(view_cls, (ViewSet, GenericViewSet)):
                    filtered.append((path, path_regex, method, callback))
                    continue

                has_serializer = hasattr(view_cls, "serializer_class") or hasattr(view_cls, "get_serializer_class")
                # allow documented views (if they specify schema overrides) - they may have attribute set by extend_schema
                has_schema_override = getattr(view_cls, "_spectacular_patched", False) or hasattr(
                    view_cls, "swagger_schema"
                )
                if not has_serializer and not has_schema_override:
                    # skip this endpoint
                    continue
        except Exception:
            # be conservative: if any check fails, keep the endpoint
            pass
        filtered.append((path, path_regex, method, callback))
    return filtered


# Postprocessing hook to ensure any path containing {job_id} has a typed path parameter
# This avoids drf-spectacular warnings when the viewset model doesn't have a matching field.
def postprocess_add_job_id_param(result, generator, **kwargs):
    paths = result.get("paths", {})
    for path, path_item in paths.items():
        if "{job_id}" not in path:
            continue
        for method_name, operation in list(path_item.items()):
            # operation is a dict for the HTTP method (get/post/...)
            if not isinstance(operation, dict):
                continue
            params = operation.setdefault("parameters", [])
            # add job_id param if missing
            if not any(p.get("name") == "job_id" for p in params):
                params.append(
                    {
                        "name": "job_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string", "format": "uuid"},
                        "description": "Job UUID",
                    }
                )
    return result


def postprocess_fix_empty_204_responses(result, generator, **kwargs):
    """Normalize 204 responses so they do not include invalid JSON schema payloads."""
    paths = result.get("paths", {})

    for _, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue

        for _, operation in path_item.items():
            if not isinstance(operation, dict):
                continue

            responses = operation.get("responses", {})
            if not isinstance(responses, dict):
                continue

            no_content = responses.get("204")
            if not isinstance(no_content, dict):
                continue

            # 204 means "No Content". Remove any accidental body definitions.
            no_content.pop("content", None)

    return result


def postprocess_add_mock_paths(result, generator, **kwargs):
    """
    Inject missing paths for Prism mock server that are not part of the standard API
    but are required by the frontend (CSR/SSR integration points).
    """
    paths = result.get("paths", {})
    # Add /api/app-config/
    if "/api/app-config/" not in paths:
        paths["/api/app-config/"] = {
            "get": {
                "operationId": "getAppConfig",
                "responses": {
                    "200": {
                        "description": "OK",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "MOCK_AUTH_ENABLED": {"type": "string", "enum": ["True"]},
                                        "theme": {"type": "string", "enum": ["neutral"]},
                                        "dateFormat": {"type": "string", "example": "dd-MM-yyyy"},
                                        "title": {"type": "string", "example": "BusinessSuite (Mock)"},
                                        "logoFilename": {"type": "string", "example": "logo_transparent.png"},
                                        "logoInvertedFilename": {
                                            "type": "string",
                                            "example": "logo_inverted_transparent.png",
                                        },
                                    },
                                    "required": ["MOCK_AUTH_ENABLED", "theme"],
                                }
                            }
                        },
                    }
                },
                "summary": "Mocked App Config for Prism",
                "tags": ["Mock"],
            }
        }
    # Add /api/mock-auth-config/
    if "/api/mock-auth-config/" not in paths:
        paths["/api/mock-auth-config/"] = {
            "get": {
                "operationId": "getMockAuthConfig",
                "responses": {
                    "200": {
                        "description": "OK",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "sub": {"type": "string", "example": "mock-user"},
                                        "username": {"type": "string", "example": "admin"},
                                        "email": {"type": "string", "example": "admin@example.com"},
                                        "is_superuser": {"type": "boolean", "example": True},
                                        "roles": {"type": "array", "items": {"type": "string"}, "example": ["admin"]},
                                    },
                                }
                            }
                        },
                    }
                },
                "summary": "Mock Auth Config",
                "tags": ["Mock"],
            }
        }
    return result
