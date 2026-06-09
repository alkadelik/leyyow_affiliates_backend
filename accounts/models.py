import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager

class AdminManager(BaseUserManager):
    def create_user(self, email, full_name, password=None, **kwargs):
        if not email:
            raise ValueError('Email is required')
        admin = self.model(
            email=self.normalize_email(email).lower(),
            full_name=full_name,
            **kwargs
        )
        admin.set_password(password)
        admin.save(using=self._db)
        return admin

    def create_superuser(self, email, full_name, password=None, **kwargs):
        kwargs.setdefault('role', 'super_admin')
        kwargs.setdefault('is_active', True)
        return self.create_user(email, full_name, password, **kwargs)


class Admin(AbstractBaseUser):
    ROLES = [('super_admin', 'Super Admin'), ('admin', 'Admin')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=255)
    role = models.CharField(max_length=32, choices=ROLES, default='admin')
    is_active = models.BooleanField(default=True)
    last_login_at = models.DateTimeField(null=True, blank=True)
    password_reset_token = models.CharField(max_length=128, null=True, blank=True)
    password_reset_expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_staff(self):
        return True

    @property
    def is_superuser(self):
        return self.role == 'super_admin'

    def has_perm(self, perm, obj=None):
        return True

    def has_module_perms(self, app_label):
        return True

    USERNAME_FIELD  = 'email'
    REQUIRED_FIELDS = ['full_name']
    objects         = AdminManager()

    class Meta:
        db_table = 'admins'

    def __str__(self):
        return f'{self.full_name} ({self.email})'


class AffiliateManager(BaseUserManager):
    def create_user(self, email, full_name, password=None, **kwargs):
        if not email:
            raise ValueError('Email is required')
        affiliate = self.model(
            email=self.normalize_email(email).lower(),
            full_name=full_name,
            **kwargs
        )
        if password:
            affiliate.set_password(password)
        affiliate.save(using=self._db)
        return affiliate


class Affiliate(AbstractBaseUser):
    STATUS_CHOICES = [
        ('invited',      'Invited'),
        ('active',       'Active'),
        ('inactive',     'Inactive'),
        ('deactivated',  'Deactivated'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=255)
    password = models.CharField(max_length=128, null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='invited')
    invite_token = models.CharField(max_length=128, null=True, blank=True)
    invite_expires_at = models.DateTimeField(null=True, blank=True)
    registered_at = models.DateTimeField(null=True, blank=True)
    last_login_at = models.DateTimeField(null=True, blank=True)
    password_reset_token = models.CharField(max_length=128, null=True, blank=True)
    password_reset_expires_at = models.DateTimeField(null=True, blank=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    deactivated_by = models.ForeignKey(
        'Admin', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='deactivated_affiliates',
        db_column='deactivated_by'
    )
    created_by = models.ForeignKey(
        'Admin',
        on_delete=models.PROTECT,
        related_name='created_affiliates',
        db_column='created_by'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']
    objects = AffiliateManager()

    class Meta:
        db_table = 'affiliates'

    def __str__(self):
        return f'{self.full_name} ({self.email})'


class AffiliateWallet(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    affiliate = models.OneToOneField(
        Affiliate,
        on_delete=models.PROTECT,
        related_name='wallet'
    )
    balance = models.IntegerField(default=0)
    total_earned = models.IntegerField(default=0)
    total_withdrawn = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'affiliate_wallets'

class AffiliateTokenBlacklist(models.Model):
    token_jti  = models.CharField(max_length=255, unique=True)
    blacklisted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'affiliate_token_blacklist'

class SystemSettings(models.Model):
    payout_auto_approve        = models.BooleanField(default=True)
    minimum_withdrawal_kobo    = models.IntegerField(default=5000000)
    tracking_base_url          = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        verbose_name = 'System Settings'

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj