import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('campaigns', '0005_merchantoffer'),
        ('tracking', '0010_conversion_payment_id_unique'),
    ]

    operations = [
        migrations.CreateModel(
            name='MerchantOfferRedemption',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('status', models.CharField(choices=[('active', 'Active'), ('ongoing', 'Ongoing'), ('exhausted', 'Exhausted'), ('expired', 'Expired'), ('forfeited', 'Forfeited')], default='active', max_length=16)),
                ('times_applied', models.IntegerField(default=0)),
                ('expires_at', models.DateTimeField()),
                ('forfeited_at', models.DateTimeField(blank=True, null=True)),
                ('exhausted_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('offer', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='redemptions', to='campaigns.merchantoffer')),
                ('merchant_lead', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='offer_redemption', to='tracking.merchantlead')),
            ],
            options={
                'db_table': 'merchant_offer_redemptions',
            },
        ),
    ]
