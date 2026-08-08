import os, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LAMS.settings')

import django
django.setup()

from organizations.models import Organization
from django.contrib.auth import get_user_model
User = get_user_model()

print("=" * 70)
print("ORGANIZATION AUDIT")
print("=" * 70)
all_orgs = Organization.objects.all().order_by('id')
print(f"Total Organizations in DB: {all_orgs.count()}")
print(f"Active Organizations: {Organization.objects.filter(status__iexact='active').count()}")
print()
for org in all_orgs:
    user_count = User.objects.filter(organization=org).count()
    print(f"  ID={org.id:3d} | Status='{org.status}' | Sub={org.sub_domain!r:20s} | Name='{org.name}' | Users={user_count}")

print()
print("=" * 70)
print("ALL USERS IN DB")
print("=" * 70)
print(f"Total Users: {User.objects.count()}")
for u in User.objects.all().order_by('id'):
    print(f"  ID={u.id:3d} | Email={u.email!r:35s} | SuperAdmin={u.is_platform_super_admin} | Org={u.organization_id} | Active={u.is_active}")

# Check for demo org specifically
print()
print("=" * 70)
print("DEMO/SEED ORGS CHECK")
print("=" * 70)
demo_names = ['Demo Organization', 'demo', 'test', 'Test Organization', 'ARV', 'Sample', 'Halyard']
for name in demo_names:
    found = Organization.objects.filter(name__icontains=name)
    if found.exists():
        for o in found:
            print(f"  FOUND POTENTIAL SEED ORG: ID={o.id} Name='{o.name}' Sub={o.sub_domain!r} Status={o.status!r}")
