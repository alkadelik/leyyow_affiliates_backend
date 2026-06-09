from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_affiliate_deactivated_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='systemsettings',
            name='minimum_withdrawal_kobo',
            field=models.IntegerField(default=5000000),
        ),
        migrations.AddField(
            model_name='systemsettings',
            name='tracking_base_url',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
    ]
