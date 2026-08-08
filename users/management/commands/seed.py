"""
Management command: python manage.py seed

Creates the minimum viable seed data for development:
  - 1 Organization (Demo Organization)
  - 3 Roles (Admin / Instructor / Student)
  - 2 Departments (Clinical / IT)
  - 4 Users (superadmin / orgadmin / instructor / student)
  - 1 sample Course owned by Demo Organization

Run this after a fresh `python manage.py migrate`.
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = 'Seed development data: org, roles, departments, users, sample course'

    def handle(self, *args, **options):
        from organizations.models import Organization, Department, Role
        from courses.models import Course, Module, Lesson

        self.stdout.write(self.style.MIGRATE_HEADING('Seeding database...'))

        # ── Organization ──────────────────────────────────────────────────────
        org, created = Organization.objects.get_or_create(
            name='Demo Organization',
            defaults={
                'company_name': 'Demo Organization Inc.',
                'entity_name': 'Demo Organization Inc.',
                'sub_domain': 'demo',
                'status': 'Active',
                'country': 'United States',
                'region': 'EMEA',
                'contact_name': 'Platform Admin',
                'contact_email': 'admin@demo.com',
            }
        )
        self.stdout.write(f'  {"Created" if created else "Exists"} organization: {org.name}')

        # ── Roles ─────────────────────────────────────────────────────────────
        admin_role, _ = Role.objects.get_or_create(
            organization=org, name='Admin',
            defaults={
                'is_default': True,
                'is_admin_role': True,
                'can_view_users': True,
                'can_create_users': True,
                'can_edit_users': True,
                'can_delete_users': True,
                'can_view_roles': True,
                'can_create_roles': True,
                'can_edit_roles': True,
                'can_delete_roles': True,
                'can_view_courses': True,
                'can_create_courses': True,
                'can_edit_courses': True,
                'can_delete_courses': True,
                'can_view_certificates': True,
                'can_create_certificates': True,
                'can_edit_certificates': True,
                'can_delete_certificates': True,
                'can_view_reports': True,
                'can_create_reports': True,
                'can_edit_reports': True,
                'can_delete_reports': True,
                'can_view_module_access': True,
                'can_create_module_access': True,
                'can_edit_module_access': True,
                'can_delete_module_access': True,
                'can_view_activity_log': True,
                'can_create_activity_log': True,
                'can_edit_activity_log': True,
                'can_delete_activity_log': True,
            }
        )
        instructor_role, _ = Role.objects.get_or_create(
            organization=org, name='Instructor',
            defaults={
                'is_default': True,
                'can_view_courses': True,
                'can_create_courses': True,
                'can_edit_courses': True,
            }
        )
        student_role, _ = Role.objects.get_or_create(
            organization=org, name='Student',
            defaults={'is_default': True}
        )
        self.stdout.write(f'  Roles: Admin, Instructor, Student')

        # ── Departments ───────────────────────────────────────────────────────
        clinical_dept, _ = Department.objects.get_or_create(organization=org, name='Clinical')
        it_dept, _ = Department.objects.get_or_create(organization=org, name='IT')
        self.stdout.write(f'  Departments: Clinical, IT')

        # ── Users ─────────────────────────────────────────────────────────────
        def make_user(username, password, **kwargs):
            if not User.objects.filter(username=username).exists():
                u = User.objects.create_user(username=username, password=password, **kwargs)
                self.stdout.write(f'  Created user: {username}')
                return u
            else:
                self.stdout.write(f'  Exists  user: {username}')
                return User.objects.get(username=username)

        make_user(
            'superadmin', 'superadmin123',
            email='superadmin@platform.com',
            first_name='Platform',
            last_name='Admin',
            is_platform_super_admin=True,
            is_staff=True,
            is_superuser=True,
            job_title='Platform Administrator',
            region='Global',
        )

        make_user(
            'orgadmin', 'orgadmin123',
            email='orgadmin@demo.com',
            first_name='Org',
            last_name='Admin',
            organization=org,
            department=clinical_dept,
            role=admin_role,
            job_title='LMS Administrator',
            region='EMEA',
            points=500,
            streak_days=3,
            level=2,
        )

        make_user(
            'instructor', 'instructor123',
            email='instructor@demo.com',
            first_name='Sam',
            last_name='Instructor',
            organization=org,
            department=clinical_dept,
            role=instructor_role,
            job_title='Senior Clinical Trainer',
            region='EMEA',
            points=1200,
            streak_days=7,
            level=5,
        )

        make_user(
            'student', 'student123',
            email='student@demo.com',
            first_name='Aris',
            last_name='Mendel',
            organization=org,
            department=clinical_dept,
            role=student_role,
            job_title='Clinical Specialist II',
            region='EMEA',
            points=7960,
            streak_days=14,
            level=12,
            badges=['compliance_champion', 'first_certificate', 'seven_day_streak'],
        )

        # ── Sample Course ─────────────────────────────────────────────────────
        if not Course.objects.filter(organization=org).exists():
            course = Course.objects.create(
                organization=org,
                title='Introduction to Workplace Safety',
                subtitle='A comprehensive guide to maintaining a safe and compliant workplace environment.',
                category='Safety',
                duration_hrs=6.0,
                passing_score=80,
                level='Intermediate',
                status='published',
                accent='var(--brand)',
            )
            mod = Module.objects.create(
                course=course,
                title='Core Safety Principles',
                summary='Foundations of workplace safety and emergency response procedures.',
                order=0,
            )
            Lesson.objects.create(module=mod, title='Safety Guidelines & Protocols', duration='6 min', type='video', video_id=0, order=0)
            Lesson.objects.create(module=mod, title='Hazard Identification', duration='12 min', type='video', video_id=1, order=1)
            Lesson.objects.create(module=mod, title='Emergency Response Best Practices', duration='4 min', type='video', video_id=2, order=2)
            Lesson.objects.create(module=mod, title='Scenario: Responding to an Incident', duration='8 min', type='scenario', interaction='branching_scenario', order=3)
            self.stdout.write(f'  Created sample course: {course.title}')
        else:
            self.stdout.write(f'  Sample course already exists, skipping.')

        self.stdout.write(self.style.SUCCESS('\nSeed complete! Login credentials:'))
        self.stdout.write('  superadmin / superadmin123  (platform super-admin, no org)')
        self.stdout.write('  orgadmin   / orgadmin123    (Demo Organization, Admin role)')
        self.stdout.write('  instructor / instructor123  (Demo Organization, Instructor role)')
        self.stdout.write('  student    / student123     (Demo Organization, Student role)')
