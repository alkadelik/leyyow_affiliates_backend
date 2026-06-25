from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracking', '0008_remove_commission_external_payment_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='conversion',
            name='is_flagged',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='conversion',
            name='flag_reason',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
