from rest_framework.permissions import BasePermission


class IsSuperAdministrator(BasePermission):
    message = "Only a super administrator can perform this action."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


class IsStaffUser(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)
