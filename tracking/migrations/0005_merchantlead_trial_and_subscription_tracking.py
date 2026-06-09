from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracking', '0004_centralwalletevent'),
    ]

    operations = [
        migrations.AlterField(
            model_name='merchantlead',
            name='status',
            field=models.CharField(
                choices=[
                    ('trial',      'Trial'),
                    ('signed_up',  'Signed Up'),
                    ('subscribed', 'Subscribed'),
                    ('expired',    'Expired'),
                    ('cancelled',  'Cancelled'),
                ],
                default='trial',
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name='merchantlead',
            name='total_amount_paid_kobo',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='merchantlead',
            name='first_subscribed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='merchantlead',
            name='first_subscription_tier',
            field=models.CharField(blank=True, max_length=32, null=True),
        ),
        migrations.RunPython(
            code=lambda apps, schema_editor: apps.get_model('tracking', 'MerchantLead').objects.filter(status='signed_up').update(status='trial'),
            reverse_code=migrations.RunPython.noop,
        ),
    ]
