from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('accounts.urls')),
    path('api/admin/campaigns/', include('campaigns.urls')),
    path('api/', include('tracking.urls')),
    path('api/', include('payouts.urls')),
    path('api/', include('analytics.urls')),
]