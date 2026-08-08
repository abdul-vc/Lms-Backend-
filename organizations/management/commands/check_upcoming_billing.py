from django.core.management.base import BaseCommand
import datetime
from django.db.models import Q
from organizations.models import BillingConfiguration, Organization
from users.models import User
from master_setup.models import Notification

class Command(BaseCommand):
    help = 'Checks all organizations for upcoming billing dates and generates notifications 5 days in advance.'

    def handle(self, *args, **kwargs):
        target_date = datetime.date.today() + datetime.timedelta(days=5)
        
        # Find billing configurations due in exactly 5 days
        upcoming_billings = BillingConfiguration.objects.filter(
            next_payment_due=target_date,
            status='active'
        )

        if not upcoming_billings.exists():
            self.stdout.write(self.style.SUCCESS(f"No billings due on {target_date}."))
            return

        # Fetch all platform super admins
        super_admins = User.objects.filter(is_platform_super_admin=True, is_active=True)

        for billing in upcoming_billings:
            org = billing.organization
            
            title = f"Billing Reminder: {org.name}"
            message = f"The next payment for {org.name} is due in 5 days (on {target_date.strftime('%b %d, %Y')}). The amount is ₹{billing.rate} for a {billing.billing_cycle} cycle."

            # Notify Super Admins
            for sa in super_admins:
                Notification.objects.create(
                    recipient=sa,
                    title=title,
                    message=message,
                    type='billing_alert'
                )

            # Notify Org Admins for this specific organization
            org_admins = User.objects.filter(
                organization=org,
                role__is_admin_role=True,
                is_active=True
            )
            for oa in org_admins:
                Notification.objects.create(
                    recipient=oa,
                    title=title,
                    message=message,
                    type='billing_alert'
                )

            self.stdout.write(self.style.SUCCESS(f"Generated notifications for {org.name}."))

        self.stdout.write(self.style.SUCCESS(f"Successfully checked upcoming billings for {target_date}."))
