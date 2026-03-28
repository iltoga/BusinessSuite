from api.services.rbac_service import get_user_rbac_claims
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


class FieldPermissionsSerializer(serializers.Serializer):
    can_read = serializers.BooleanField()
    can_write = serializers.BooleanField()


class RbacPermissionsSerializer(serializers.Serializer):
    # Dynamic dicts. In DRF, we can just use DictField to let spectacular know it's a map.
    menus = serializers.DictField(child=serializers.BooleanField())
    fields = serializers.DictField(child=FieldPermissionsSerializer())


class RbacViewSet(viewsets.ViewSet):
    """
    Read-only viewset providing current user's evaluated RBAC permissions.
    """
    
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: RbacPermissionsSerializer})
    @action(detail=False, methods=["get"], url_path="my-permissions")
    def my_permissions(self, request):
        """
        Returns a compiled dictionary of all menu and field access rules
        that apply to the current authenticated user.
        """
        claims = get_user_rbac_claims(request.user)
        return Response(claims, status=status.HTTP_200_OK)
