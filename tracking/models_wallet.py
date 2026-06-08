import uuid
from django.db import models


class CentralWallet(models.Model):
    id                          = models.AutoField(primary_key=True)
    balance                     = models.IntegerField(default=0)
    total_commissions_allocated = models.IntegerField(default=0)
    total_payouts_made          = models.IntegerField(default=0)
    updated_at                  = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'central_wallet'

    def save(self, *args, **kwargs):
        self.id = 1  # Always single row
        super().save(*args, **kwargs)