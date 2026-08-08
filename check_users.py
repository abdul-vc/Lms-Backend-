import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LAMS.settings')
django.setup()

from django.contrib.auth import get_user_model
from organizations.models import Organization, Site

User = get_user_model()

print("ORGANIZATIONS:", list(Organization.objects.values_list('id', 'name')))
print("SITES:", list(Site.objects.values_list('id', 'name')))
print("TOTAL USERS:", User.objects.count())
print("USERS LIST:")
for u in User.objects.all():
    print(f"  - ID: {u.id}, Email: {u.email}, Name: {u.full_name}, Org: {u.organization_id}, Active: {u.is_active}, SuperAdmin: {u.is_platform_super_admin}")
