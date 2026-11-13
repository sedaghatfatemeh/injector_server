from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from devices.views import CustomerViewSet, DeviceViewSet, EventViewSet, ReleaseViewSet, dashboard_summary, device_check_in, ingest_events, staff_login, staff_logout, update_manifest, update_result

router = DefaultRouter()
router.register("customers", CustomerViewSet, basename="customer")
router.register("devices", DeviceViewSet, basename="device")
router.register("events", EventViewSet, basename="event")
router.register("releases", ReleaseViewSet, basename="release")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include(router.urls)),
    path("api/v1/auth/login/", staff_login, name="staff-login"),
    path("api/v1/auth/logout/", staff_logout, name="staff-logout"),
    path("api/v1/dashboard/summary/", dashboard_summary, name="dashboard-summary"),
    path("api/v1/device/check-in/", device_check_in, name="device-check-in"),
    path("api/v1/device/events/", ingest_events, name="device-ingest-events"),
    path("api/v1/device/update-manifest/", update_manifest, name="device-update-manifest"),
    path("api/v1/device/update-result/", update_result, name="device-update-result"),
]
