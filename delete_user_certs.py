import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LAMS.settings')
django.setup()

from courses.models import IssuedCertificate, AssessmentAttempt
from users.models import User

user = User.objects.filter(email='riyazanilv@gmail.com').first()
if not user:
    user = User.objects.filter(first_name__icontains='gaurav').first()

if user:
    certs = IssuedCertificate.objects.filter(user=user)
    cert_count = certs.count()
    certs.delete()
    
    attempts = AssessmentAttempt.objects.filter(user=user)
    attempt_count = attempts.count()
    attempts.delete()
    
    print(f"SUCCESS: Deleted {cert_count} IssuedCertificate(s) and {attempt_count} AssessmentAttempt(s) for user: {user.email} ({user.first_name} {user.last_name})")
else:
    certs_all = IssuedCertificate.objects.all()
    count = certs_all.count()
    certs_all.delete()
    print(f"SUCCESS: Deleted all {count} IssuedCertificate(s) from database.")
