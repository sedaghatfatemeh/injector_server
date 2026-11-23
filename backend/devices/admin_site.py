from math import ceil

from django.contrib.admin import AdminSite
from django.contrib.admin.forms import AdminAuthenticationForm
from django.db import transaction
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache

from .models import AuditEntry
from .access import staff_role
from .throttling import LoginThrottle


class SuperAdministratorAuthenticationForm(AdminAuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if staff_role(user) != "super_admin":
            raise self.get_invalid_login_error()


class SuperAdministratorAdminSite(AdminSite):
    login_form = SuperAdministratorAuthenticationForm

    def has_permission(self, request):
        return staff_role(request.user) == "super_admin"

    @method_decorator(never_cache)
    def login(self, request, extra_context=None):
        if request.method != "POST":
            return super().login(request, extra_context)
        throttle = LoginThrottle()
        if not throttle.allow_request(request, self):
            return JsonResponse({"detail": "Too many sign-in attempts."}, status=429,
                                headers={"Retry-After": str(ceil(throttle.wait()))})
        with transaction.atomic():
            response = super().login(request, extra_context)
            successful = response.status_code == 302 and self.has_permission(request)
            AuditEntry.objects.create(
                actor=request.user if successful else None,
                action="staff.signed_in" if successful else "staff.sign_in_failed",
                target_type="user", target_id=str(request.user.pk) if successful else "",
                outcome="success" if successful else "denied", details={"source": "django_admin"},
            )
        return response

    @method_decorator(never_cache)
    def logout(self, request, extra_context=None):
        if request.method != "POST":
            return super().logout(request, extra_context)
        with transaction.atomic():
            AuditEntry.objects.create(actor=request.user, action="staff.signed_out", target_type="user",
                                      target_id=str(request.user.pk), details={"source": "django_admin"})
            return super().logout(request, extra_context)
