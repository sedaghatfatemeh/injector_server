from django.contrib import admin
from django.urls import include, path
from django.views.decorators.http import require_GET
from rest_framework.routers import DefaultRouter
from devices.views import CustomerViewSet, DeviceViewSet, EventViewSet, ReleaseViewSet, csrf_token, dashboard_summary, device_check_in, ingest_events, staff_login, staff_logout, staff_session, update_manifest, update_result
from django.http import JsonResponse
from django.db import connection
from devices.views import StaffUserViewSet
from devices.portal import CustomerDeviceViewSet, CustomerSummary, CustomerUserViewSet
from .frontend import console

router = DefaultRouter()
router.register("customers", CustomerViewSet, basename="customer")
router.register("devices", DeviceViewSet, basename="device")
router.register("events", EventViewSet, basename="event")
router.register("releases", ReleaseViewSet, basename="release")
router.register("staff-users", StaffUserViewSet, basename="staff-user")
router.register("customer-users", CustomerUserViewSet, basename="customer-user")
router.register("customer/devices", CustomerDeviceViewSet, basename="customer-device")


@require_GET
def ready(request):
    try:
        connection.ensure_connection()
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})

urlpatterns = [
    path("", console, name="console"),
    path("customer/devices", console, name="customer-console"),
    path("customer/devices/", console),
    path("customer/devices/<int:device_id>", console, name="customer-console-detail"),
    path("customer/devices/<int:device_id>/", console),
    path("health/live/", lambda request: JsonResponse({"status": "ok"}), name="health-live"),
    path("health/ready/", ready, name="health-ready"),
    path("admin/", admin.site.urls),
    path("api/v1/", include(router.urls)),
    path("api/v1/customer/summary/", CustomerSummary.as_view(), name="customer-summary"),
    path("api/v1/auth/login/", staff_login, name="staff-login"),
    path("api/v1/auth/csrf/", csrf_token, name="staff-csrf"),
    path("api/v1/auth/logout/", staff_logout, name="staff-logout"),
    path("api/v1/auth/session/", staff_session, name="staff-session"),
    path("api/v1/dashboard/summary/", dashboard_summary, name="dashboard-summary"),
    path("api/v1/device/check-in/", device_check_in, name="device-check-in"),
    path("api/v1/device/events/", ingest_events, name="device-ingest-events"),
    path("api/v1/device/update-manifest/", update_manifest, name="device-update-manifest"),
    path("api/v1/device/update-result/", update_result, name="device-update-result"),
]
