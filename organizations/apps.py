from django.apps import AppConfig

class OrganizationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'organizations'

    def ready(self):
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                columns = [col.name for col in connection.introspection.get_table_description(cursor, 'organizations_organization')]
                if 'subdomain_routing_enabled' not in columns:
                    cursor.execute("ALTER TABLE organizations_organization ADD COLUMN subdomain_routing_enabled BOOLEAN DEFAULT 1")
        except Exception as e:
            print("Auto-alter organizations_organization error:", e)
