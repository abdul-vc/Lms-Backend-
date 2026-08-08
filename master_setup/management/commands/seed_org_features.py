from django.core.management.base import BaseCommand
from organizations.models import Organization
from organizations.services import seed_org_feature_access


class Command(BaseCommand):
    help = 'Backfill OrganizationFeatureAccess rows (enabled=True) for all existing organizations.'

    def handle(self, *args, **options):
        orgs = Organization.objects.all()
        for org in orgs:
            seed_org_feature_access(org)
            self.stdout.write(f'  OK: Seeded feature access for: {org.name}')
        self.stdout.write(self.style.SUCCESS(f'Done. {orgs.count()} organization(s) processed.'))
