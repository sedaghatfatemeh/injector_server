from rest_framework.permissions import BasePermission
from django.contrib.auth import get_user_model

from .models import AuditEntry
from .access import browser_identity, staff_role


class AuditedStaffActionsMixin:
    audit_target_type = ""

    def permission_denied(self, request, message=None, code=None):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            actor = request.user if isinstance(request.user, get_user_model()) else None
            try:
                target = int(self.kwargs.get("pk", ""))
                target_id = str(target) if 0 < target <= 2**63 - 1 else ""
            except (TypeError, ValueError):
                target_id = ""
            AuditEntry.objects.create(
                actor=actor, action="authorization.denied", target_type=self.audit_target_type,
                target_id=target_id, outcome="denied", details={"operation": self.action, "source": "staff_api"},
            )
        return super().permission_denied(request, message=message, code=code)


class IsSuperAdministrator(BasePermission):
    message = "Only a super administrator can perform this action."

    def has_permission(self, request, view):
        return staff_role(request.user) == "super_admin"


class IsStaffUser(BasePermission):
    def has_permission(self, request, view):
        return staff_role(request.user) is not None


class IsBrowserUser(BasePermission):
    def has_permission(self, request, view):
        request.browser_identity = browser_identity(request.user)
        return request.browser_identity is not None
