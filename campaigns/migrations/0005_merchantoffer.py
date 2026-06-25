import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('campaigns', '0004_campaign_type_subscriber_tiers'),
    ]

    operations = [
        migrations.CreateModel(
            name='MerchantOffer',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('applicable_to', models.CharField(choices=[('trial', 'Trial'), ('subscription', 'Subscription')], max_length=16)),
                ('type', models.CharField(choices=[('extension', 'Extension'), ('discount', 'Discount')], max_length=16)),
                ('extension_days', models.IntegerField(blank=True, null=True)),
                ('discount_subtype', models.CharField(blank=True, choices=[('amount', 'Amount'), ('percentage', 'Percentage')], max_length=16, null=True)),
                ('discount_value', models.IntegerField(blank=True, null=True)),
                ('discount_recurrence', models.CharField(blank=True, choices=[('once', 'Once'), ('n_times', 'N Times'), ('forever', 'Forever')], max_length=16, null=True)),
                ('discount_recurrence_count', models.IntegerField(blank=True, null=True)),
                ('has_lifetime_condition', models.BooleanField(default=False)),
                ('condition_type', models.CharField(blank=True, max_length=32, null=True)),
                ('condition_threshold', models.IntegerField(blank=True, null=True)),
                ('merchant_redemption_window_days', models.IntegerField()),
                ('offer_valid_from', models.DateTimeField()),
                ('offer_valid_until', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('campaign', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='offers', to='campaigns.campaign')),
            ],
            options={
                'db_table': 'merchant_offers',
                'ordering': ['-created_at'],
            },
        ),
    ]
