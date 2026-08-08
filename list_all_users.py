import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LAMS.settings')
django.setup()

from django.contrib.auth import get_user_model
User = get_user_model()

print(f"TOTAL USERS IN DATABASE: {User.objects.count()}")
print("-" * 60)
for u in User.objects.all():
    print(f"ID: {u.id} | Email: {u.email} | Name: '{u.full_name}' | Username: '{u.username}' | Org: {u.organization_id} | Active: {u.is_active} | SuperAdmin: {u.is_platform_super_admin} | LastLogin: {u.last_login}")
print("-" * 60)
