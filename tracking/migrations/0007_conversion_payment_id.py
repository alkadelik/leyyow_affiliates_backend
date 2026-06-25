from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracking', '0006_conversion_external_event_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='conversion',
            name='payment_id',
            field=models.CharField(blank=True, max_length=128, null=True),
        ),
    ]
