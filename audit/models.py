import uuid
from django.db import models


class AuditLog(models.Model):
    ACTOR_TYPES = [('admin', 'Admin'), ('affiliate', 'Affiliate'), ('system', 'System')]

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor_type  = models.CharField(max_length=16, choices=ACTOR_TYPES)
    actor_id    = models.UUIDField(null=True, blank=True)
    action      = models.CharField(max_length=64)
    entity_type = models.CharField(max_length=32)
    entity_id   = models.UUIDField(null=True, blank=True)
    changes     = models.JSONField(null=True, blank=True)
    metadata    = models.JSONField(null=True, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'audit_log'
        ordering = ['-created_at']