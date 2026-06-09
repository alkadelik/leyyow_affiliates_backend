from django.db import migrations, models


def inactive_to_deactivated(apps, schema_editor):
    Affiliate = apps.get_model('accounts', 'Affiliate')
    Affiliate.objects.filter(status='inactive').update(status='deactivated')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_systemsettings'),
    ]

    operations = [
        migrations.AlterField(
            model_name='affiliate',
            name='status',
            field=models.CharField(
                choices=[
                    ('invited',     'Invited'),
                    ('active',      'Active'),
                    ('inactive',    'Inactive'),
                    ('deactivated', 'Deactivated'),
                ],
                default='invited',
                max_length=16,
            ),
        ),
        migrations.RunPython(inactive_to_deactivated, migrations.RunPython.noop),
    ]
