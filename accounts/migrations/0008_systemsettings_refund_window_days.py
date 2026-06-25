from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0007_systemsettings_transfer_fee'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemsettings',
            name='refund_window_days',
            field=models.IntegerField(default=30),
        ),
    ]
