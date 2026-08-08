from django.apps import AppConfig


class CoursesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'courses'

    def ready(self):
        try:
            from django.core.management import call_command
            call_command('migrate', 'courses', interactive=False)
        except Exception as e:
            print(f"[AUTO-MIGRATE COURSES] {e}")

