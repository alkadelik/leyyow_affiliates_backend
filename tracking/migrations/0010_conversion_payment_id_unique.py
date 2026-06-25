from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tracking', '0009_conversion_flagging'),
    ]

    operations = [
        migrations.AlterField(
            model_name='conversion',
            name='payment_id',
            field=models.CharField(blank=True, max_length=128, null=True, unique=True),
        ),
    ]
