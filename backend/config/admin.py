from django.contrib.admin.apps import AdminConfig


class SuperAdministratorAdminConfig(AdminConfig):
    default_site = "devices.admin_site.SuperAdministratorAdminSite"
