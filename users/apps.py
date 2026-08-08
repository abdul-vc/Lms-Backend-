from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'users'

    def ready(self):
        try:
            from django.core.management import call_command
            call_command('migrate', 'users', interactive=False)
        except Exception as e:
            print(f"[AUTO-MIGRATE USERS] {e}")

