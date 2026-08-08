import os
import json
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'LAMS.settings')
django.setup()

from users.models import User
from users.serializers import UserSerializer

def export_all_users():
    users = User.objects.all()
    serializer = UserSerializer(users, many=True)
    user_data = serializer.data

    output_path = os.path.join(os.path.dirname(__file__), 'data.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(user_data, f, indent=2, default=str)

    print(f"Successfully exported {len(user_data)} user records to {output_path}")

if __name__ == '__main__':
    export_all_users()
