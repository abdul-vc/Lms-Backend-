import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LAMS.settings')
django.setup()

from organizations.models import Organization
from organizations.emails import send_tenant_welcome_email

org = Organization.objects.filter(sub_domain='vtravelofficials').first()
if not org:
    org = Organization.objects.first()

print(f"Testing SMTP email for Organization: {org.name} ({org.contact_email})")
success, msg = send_tenant_welcome_email(
    org=org,
    recipient_email=org.contact_email or 'vtravelofficials@gmail.com',
    admin_username=org.contact_email or 'vtravelofficials@gmail.com',
    raw_password='TempPass@2026'
)

print(f"Result: Success={success}")
print(f"Message: {msg}")
