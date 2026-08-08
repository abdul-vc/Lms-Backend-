from rest_framework import serializers
from .models import ImportJob

class ImportJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportJob
        fields = '__all__'
        read_only_fields = ['organization', 'created_by', 'status', 'progress_percent', 'error_log', 'created_at']
