from rest_framework.permissions import BasePermission


class IsAnyAdmin(BasePermission):
    """Any authenticated admin (admin or super_admin). Use on all admin portal views."""
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and hasattr(request.user, 'role')
            and request.user.role in ('admin', 'super_admin')
        )


class IsSuperAdmin(BasePermission):
    """super_admin only. Use on admin management endpoints."""
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and hasattr(request.user, 'role')
            and request.user.role == 'super_admin'
        )


class IsAffiliate(BasePermission):
    """Authenticated affiliate."""
    def has_permission(self, request, view):
        from accounts.models import Affiliate
        return (
            request.user.is_authenticated
            and isinstance(request.user, Affiliate)
        )