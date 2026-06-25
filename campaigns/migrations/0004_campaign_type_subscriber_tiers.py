from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('campaigns', '0003_alter_campaign_commission_value'),
    ]

    operations = [
        migrations.AlterField(
            model_name='campaign',
            name='commission_type',
            field=models.CharField(
                blank=True,
                choices=[
                    ('flat_fee', 'Flat Fee'),
                    ('percentage', 'Percentage'),
                    ('percentage_capped', 'Percentage Capped'),
                ],
                max_length=24,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='campaign',
            name='campaign_type',
            field=models.CharField(
                choices=[('fixed', 'Fixed'), ('tiered', 'Tiered')],
                default='fixed',
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name='campaign',
            name='subscriber_tiers',
            field=models.JSONField(blank=True, null=True),
        ),
    ]
