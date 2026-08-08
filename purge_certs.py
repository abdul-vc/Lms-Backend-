import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LAMS.settings')
django.setup()

from courses.models import IssuedCertificate, AssessmentAttempt, ScormTracking

c1 = IssuedCertificate.objects.all().delete()
c2 = AssessmentAttempt.objects.all().delete()
c3 = ScormTracking.objects.all().delete()

print(f"SUCCESSFULLY PURGED DATABASE:")
print(f"IssuedCertificates deleted: {c1}")
print(f"AssessmentAttempts deleted: {c2}")
print(f"ScormTracking deleted: {c3}")
