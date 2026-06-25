from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('campaigns', '0005_merchantoffer'),
    ]

    operations = [
        migrations.AddField(
            model_name='campaign',
            name='tiered_period_days',
            field=models.IntegerField(blank=True, default=90, null=True),
        ),
    ]
