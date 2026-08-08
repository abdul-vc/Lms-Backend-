from rest_framework import serializers
from .models import (
    LessonBlockTree, LessonBlock, ReadingContent,
    InteractionBlock, KCQuestion, ScenarioNode, AuthoringAsset, CourseVersion
)

class ReadingContentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReadingContent
        fields = '__all__'

class InteractionBlockSerializer(serializers.ModelSerializer):
    class Meta:
        model = InteractionBlock
        fields = '__all__'

class KCQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = KCQuestion
        fields = '__all__'
        read_only_fields = ['organization']

class ScenarioNodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScenarioNode
        fields = '__all__'

class LessonBlockSerializer(serializers.ModelSerializer):
    reading_payload = ReadingContentSerializer(read_only=True)
    interaction_payload = InteractionBlockSerializer(read_only=True)
    kc_questions = KCQuestionSerializer(many=True, read_only=True)
    scenario_nodes = ScenarioNodeSerializer(many=True, read_only=True)

    class Meta:
        model = LessonBlock
        fields = '__all__'
        read_only_fields = ['organization']

class LessonBlockTreeSerializer(serializers.ModelSerializer):
    blocks = LessonBlockSerializer(many=True, read_only=True)

    class Meta:
        model = LessonBlockTree
        fields = '__all__'

class AuthoringAssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuthoringAsset
        fields = '__all__'
        read_only_fields = ['organization', 'file_hash', 'original_filename', 'mime_type', 'file_size']

class CourseVersionSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)

    class Meta:
        model = CourseVersion
        fields = '__all__'

