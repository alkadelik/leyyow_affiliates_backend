from audit.models import AuditLog


def log_action(actor_type, action, entity_type,
               actor_id=None, entity_id=None,
               changes=None, metadata=None):
    AuditLog.objects.create(
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        changes=changes,
        metadata=metadata,
    )