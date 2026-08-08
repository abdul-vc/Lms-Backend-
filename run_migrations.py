import os
import sys

# Add backend directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "LAMS.settings")
django.setup()

from django.core.management import call_command

print("Making migrations...")
call_command('makemigrations', 'master_setup', 'organizations')

print("Migrating...")
call_command('migrate')

print("Seeding workspaces...")
call_command('seed_workspaces')
