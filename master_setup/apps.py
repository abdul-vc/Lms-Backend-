from django.apps import AppConfig

class MasterSetupConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'master_setup'

    def ready(self):
        # Automatically run migrations to sync schema when Django starts
        import sys
        if 'runserver' in sys.argv or 'gunicorn' in sys.argv or 'uvicorn' in sys.argv or any('manage.py' in arg for arg in sys.argv):
            try:
                from django.core.management import call_command
                call_command('makemigrations', 'master_setup', 'organizations', 'courses', 'users', interactive=False)
                call_command('migrate', interactive=False)
                call_command('seed_workspaces', interactive=False)
            except Exception as e:
                print(f"Auto migration warning: {e}")
