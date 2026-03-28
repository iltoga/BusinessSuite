from api.services.rbac_service import get_user_rbac_claims


class RbacFieldFilterMixin:
    """
    Generic mixin to dynamically redact fields from the serializer
    if the requesting user lacks read/write access based on RBAC rules.
    """

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get("request")

        # During schema generation (Spectacular), request might be None.
        if not request or not hasattr(request, "user"):
            return fields

        claims = get_user_rbac_claims(request.user)

        # Allow serializers to override the "model_name" for RBAC checks
        model_name = getattr(self.Meta, "rbac_model_name", getattr(self.Meta, "model", None))
        if not model_name:
            return fields

        if hasattr(model_name, "_meta"):
            model_name = model_name._meta.model_name
        elif isinstance(model_name, type):
            model_name = model_name.__name__.lower()

        # Determine if the current request is for writing
        is_write = request.method in ["POST", "PUT", "PATCH"]

        for field_name in list(fields.keys()):
            rule_key = f"{model_name}.{field_name}"
            if rule_key in claims.get("fields", {}):
                rule = claims["fields"][rule_key]
                if is_write and not rule.get("can_write", True):
                    fields.pop(field_name, None)
                elif not is_write and not rule.get("can_read", True):
                    fields.pop(field_name, None)

        return fields
