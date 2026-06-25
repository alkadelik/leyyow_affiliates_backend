from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracking', '0005_merchantlead_trial_and_subscription_tracking'),
    ]

    operations = [
        migrations.AddField(
            model_name='conversion',
            name='external_event_id',
            field=models.CharField(blank=True, max_length=128, null=True, unique=True),
        ),
    ]
