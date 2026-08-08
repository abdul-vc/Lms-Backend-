import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LAMS.settings')
django.setup()

from organizations.models import Organization
from organizations.emails import send_tenant_welcome_email

for org in Organization.objects.all()[:3]:
    print(f"Testing for Org ID={org.id}, Name={org.name}, Email={org.contact_email}")
    success, msg = send_tenant_welcome_email(org=org, recipient_email=org.contact_email, raw_password='TempPass@2026')
    print(f"  Success: {success}, Message: {msg}")
