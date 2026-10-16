"""
Management command: python manage.py bootstrap_showcase_superadmin

Idempotent bootstrap mechanism for the designated LMS Showcase Platform Superadmin account.
Never hardcodes passwords or secrets; consumes credentials exclusively from
server-side environment variables / Django settings:
  - LMS_SHOWCASE_SUPERADMIN_EMAIL (default: superadmin@gmail.com)
  - LMS_SHOWCASE_SUPERADMIN_PASSWORD (initial password)
Ensures genuine application-level global Platform Superadmin permissions (is_platform_super_admin=True,
is_staff=True, is_superuser=True, is_active=True) required by the LMS authorization system.
"""

import os
import logging
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = 'Idempotently bootstrap or verify the designated LMS Showcase Platform Superadmin account'

    def add_arguments(self, parser):
        parser.add_argument(
            '--email',
            type=str,
            default='',
            help='Override the designated superadmin email (defaults to LMS_SHOWCASE_SUPERADMIN_EMAIL setting)'
        )
        parser.add_argument(
            '--password',
            type=str,
            default='',
            help='Initial password (defaults to LMS_SHOWCASE_SUPERADMIN_PASSWORD setting)'
        )
        parser.add_argument(
            '--force-password',
            action='store_true',
            help='Force-update password even if a usable password already exists'
        )

    def handle(self, *args, **options):
        designated_email = (
            options.get('email')
            or getattr(settings, 'LMS_SHOWCASE_SUPERADMIN_EMAIL', '')
            or os.getenv('LMS_SHOWCASE_SUPERADMIN_EMAIL', 'superadmin@gmail.com')
        ).strip().lower()

        raw_password = (
            options.get('password')
            or getattr(settings, 'LMS_SHOWCASE_SUPERADMIN_PASSWORD', '')
            or os.getenv('LMS_SHOWCASE_SUPERADMIN_PASSWORD', '')
        ).strip()

        force_password = options.get('force_password', False)

        if not designated_email:
            self.stderr.write(self.style.ERROR("Error: Showcase superadmin email is required."))
            return

        with transaction.atomic():
            user = (
                User.objects.filter(email__iexact=designated_email).first()
                or User.objects.filter(username__iexact=designated_email).first()
            )

            created = False
            if not user:
                user = User.objects.create(
                    username=designated_email,
                    email=designated_email,
                    first_name='Platform',
                    last_name='Superadmin',
                    is_platform_super_admin=True,
                    is_staff=True,
                    is_superuser=True,
                    is_active=True,
                )
                created = True
                if raw_password:
                    user.set_password(raw_password)
                else:
                    user.set_unusable_password()
                user.save()
                self.stdout.write(self.style.SUCCESS(f"Created new Showcase Platform Superadmin account: {designated_email}"))
            else:
                # Update permissions to guarantee genuine platform-level superadmin privileges
                needs_save = False
                if not user.is_platform_super_admin:
                    user.is_platform_super_admin = True
                    needs_save = True
                if not user.is_staff:
                    user.is_staff = True
                    needs_save = True
                if not user.is_superuser:
                    user.is_superuser = True
                    needs_save = True
                if not user.is_active:
                    user.is_active = True
                    needs_save = True

                # Password handling: never reset on every launch/bootstrap unless forced or unusable
                if raw_password and (force_password or not user.has_usable_password()):
                    user.set_password(raw_password)
                    needs_save = True

                if needs_save:
                    user.save()
                    self.stdout.write(self.style.SUCCESS(f"Verified & updated Showcase Platform Superadmin permissions for: {designated_email}"))
                else:
                    self.stdout.write(self.style.SUCCESS(f"Showcase Platform Superadmin is already active and verified: {designated_email}"))

            # Ensure ExternalUserMapping for VibeConnect integration if available
            try:
                from organizations.models import ExternalUserMapping, ExternalTenantMapping
                demo_tenant = ExternalTenantMapping.objects.filter(provider='vibeconnect').first()
                if demo_tenant:
                    external_user_id = os.getenv('LMS_SHOWCASE_SUPERADMIN_EXTERNAL_ID', '2a91cb1c-8f5d-4492-b4a4-1ce5ee82a700').strip()
                    mapping, m_created = ExternalUserMapping.objects.get_or_create(
                        provider='vibeconnect',
                        external_user_id=external_user_id,
                        defaults={
                            'user': user,
                            'organization': demo_tenant.organization,
                            'status': 'active',
                        }
                    )
                    if mapping.user_id != user.id:
                        mapping.user = user
                        mapping.status = 'active'
                        mapping.save(update_fields=['user', 'status'])
            except Exception as map_err:
                logger.warning(f"Note: Could not sync external user mapping: {map_err}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Showcase Superadmin Ready: User ID {user.id} | Email: {user.email} | "
                f"Superadmin: {user.is_platform_super_admin} | Superuser: {user.is_superuser} | Staff: {user.is_staff}"
            )
        )
