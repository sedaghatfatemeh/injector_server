import re

from django.db.models import CharField, Count, Func, Q, Value
from rest_framework.exceptions import ValidationError
from rest_framework.filters import OrderingFilter, SearchFilter

from .models import Device, DeviceEvent


PHONE_DIGITS = "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩"
ASCII_DIGITS = "01234567890123456789"


def normalize_phone(value):
    return re.sub(r"[\s().-]+", "", value.translate(str.maketrans(PHONE_DIGITS, ASCII_DIGITS)))


class CustomerSearchFilter(SearchFilter):
    def filter_queryset(self, request, queryset, view):
        filtered = super().filter_queryset(request, queryset, view)
        needle = normalize_phone(request.query_params.get(self.search_param, ""))
        if not re.fullmatch(r"\+?[0-9]+", needle):
            return filtered
        translated = Func("contact_phone", Value(PHONE_DIGITS), Value(ASCII_DIGITS), function="translate", output_field=CharField())
        normalized = Func(translated, Value(r"[\s().-]+"), Value(""), Value("g"), function="regexp_replace", output_field=CharField())
        return queryset.alias(_phone_search=normalized).filter(Q(pk__in=filtered.values("pk")) | Q(_phone_search__icontains=needle))


class InventoryOrderingFilter(OrderingFilter):
    def get_ordering(self, request, queryset, view):
        ordering = super().get_ordering(request, queryset, view)
        if ordering and not any(field.lstrip("-") in {"id", "pk"} for field in ordering):
            return [*ordering, "pk"]
        return ordering


def boolean_parameter(request, name, default=False):
    value = request.query_params.get(name)
    if value is None:
        return default
    if value not in {"true", "false"}:
        raise ValidationError({name: "Use true or false."})
    return value == "true"


def device_inventory():
    return Device.objects.select_related("customer").annotate(
        active_fault_count=Count("faults", filter=Q(faults__state=DeviceEvent.State.ACTIVE), distinct=True),
    ).order_by("serial_number", "pk")


CUSTOMER_AUDIT_FIELDS = ("organization_name", "contact_name", "contact_email", "contact_phone", "address", "notes", "is_archived")
DEVICE_AUDIT_FIELDS = ("serial_number", "model_name", "customer_id", "software_version", "location", "site_contact_name", "site_contact_phone", "is_archived")


def snapshot(instance, fields):
    return {field: getattr(instance, field) for field in fields}
