import os
import django
from django.core.management import call_command

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LAMS.settings')
django.setup()

call_command('makemigrations', 'master_setup')
call_command('makemigrations', 'organizations')
