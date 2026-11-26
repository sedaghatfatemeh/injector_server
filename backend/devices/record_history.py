"""Minimal staff-only lifecycle summaries, batched once per serialized page."""
from rest_framework import serializers

from .access import staff_role
from .models import AuditEntry


RULES = {
    "customer": {"created": {"customer.created"}, "edited": {"customer.updated", "customer.archived"}, "archived": {"customer.archived"}},
    "device": {"created": {"device.registered"}, "edited": {"device.updated", "device.archived"}, "archived": {"device.archived"}},
    "device_model": {"created": {"device_model.created"}, "edited": {"device_model.updated"}},
    "user": {"created": {"staff.created", "customer_user.created"}, "edited": {"staff.updated", "customer_user.status_changed"}},
    "release": {"created": {"release.published"}, "edited": {"release.withdrawn"}, "withdrawn": {"release.withdrawn"}},
}


def actor_label(actor):
    return (actor.get_full_name().strip() or f"کاربر #{actor.pk}") if actor else None


def stamp(at, by=None):
    return {"at": serializers.DateTimeField().to_representation(at) if at else None, "by": by}


def load_history(kind, instances):
    instances = list(instances)
    rules = RULES[kind]
    actions = set().union(*rules.values())
    result = {str(instance.pk): {"created": None, "edited": None, "archived": None, "withdrawn": None} for instance in instances}
    entries = AuditEntry.objects.filter(target_type=kind, target_id__in=result, outcome="success", action__in=actions).select_related("actor").order_by("created_at", "pk")
    for entry in entries:
        summary = result[entry.target_id]
        for operation, names in rules.items():
            if entry.action in names and (operation != "created" or summary[operation] is None):
                summary[operation] = stamp(entry.created_at, entry.actor_label or actor_label(entry.actor))
    for instance in instances:
        summary = result[str(instance.pk)]
        # Native creation dates are authoritative even without an audit record.
        created_at = getattr(instance, "created_at", None) or getattr(instance, "date_joined", None)
        if summary["created"] is None:
            creator = actor_label(instance.created_by) if kind == "release" else None
            summary["created"] = stamp(created_at, creator)
        elif created_at:
            summary["created"]["at"] = stamp(created_at)["at"]
    return result


class RecordHistorySerializerMixin(serializers.Serializer):
    record_history = serializers.SerializerMethodField()
    history_target_type = ""

    def get_record_history(self, instance):
        # Never turn a staff serializer into a customer/device audit endpoint.
        request = self.context.get("request")
        if "_history_allowed" not in self.context:
            self.context["_history_allowed"] = request is not None and staff_role(request.user) is not None
        if not self.context["_history_allowed"]:
            return None
        instances = self.parent.instance if isinstance(self.parent, serializers.ListSerializer) else [instance]
        instances = list(instances)
        key = (self.history_target_type, tuple(obj.pk for obj in instances))
        cache = self.context.setdefault("_record_history", {})
        if key not in cache:
            cache[key] = load_history(self.history_target_type, instances)
        return cache[key][str(instance.pk)]
