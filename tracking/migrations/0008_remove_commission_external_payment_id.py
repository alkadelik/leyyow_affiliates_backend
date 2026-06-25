from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('tracking', '0007_conversion_payment_id'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='commission',
            name='external_payment_id',
        ),
    ]
