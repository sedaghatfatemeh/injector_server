"""Resolve browser eligibility from current database facts, not session claims."""

from django.contrib.auth import get_user_model

from .models import CustomerMembership


def customer_membership(user):
    if not isinstance(user, get_user_model()) or not user.is_active or user.is_staff or user.is_superuser:
        return None
    if user.groups.filter(name="support").exists():
        return None
    return CustomerMembership.objects.select_related("customer").filter(
        user_id=user.pk, customer__is_archived=False,
    ).first()


def staff_role(user):
    if not isinstance(user, get_user_model()) or not user.is_active or not user.is_staff:
        return None
    if CustomerMembership.objects.filter(user_id=user.pk).exists():
        return None
    if user.is_superuser:
        return "super_admin"
    if user.groups.filter(name="support").exists():
        return "support"
    return None


def browser_identity(user):
    role = staff_role(user)
    if role:
        return {"email": user.email, "role": role}
    membership = customer_membership(user)
    if membership:
        return {"email": user.email, "role": "customer",
                "organization": {"id": membership.customer_id, "name": membership.customer.organization_name}}
    return None
