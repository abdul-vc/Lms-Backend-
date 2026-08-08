import uuid
from django.db import models

def org_asset_path(instance, filename):
    org_id = instance.organization_id if instance.organization_id else 'common'
    return f"orgs/{org_id}/assets/{instance.id}_{filename}"

BLOCK_TYPE_CHOICES = [
    ('heading', 'Heading'),
    ('paragraph', 'Paragraph'),
    ('video', 'Video'),
    ('image', 'Image'),
    ('audio', 'Audio'),
    ('table', 'Table'),
    ('quote', 'Quote'),
    ('code', 'Code'),
    ('callout', 'Callout'),
    ('pdf', 'PDF'),
    ('interaction', 'Interaction'),
    ('quiz', 'Quiz'),
    ('scenario', 'Scenario'),
]

INTERACTION_TYPE_CHOICES = [
    ('tabs', 'Tabs'),
    ('accordion', 'Accordion'),
    ('timeline', 'Timeline'),
    ('flashcards', 'Flashcards'),
    ('hotspots', 'Hotspots'),
    ('image_compare', 'Image Compare'),
    ('before_after', 'Before-After'),
    ('clickable_cards', 'Clickable Cards'),
    ('process_flow', 'Process Flow'),
    ('drag_drop', 'Drag & Drop'),
    ('sorting', 'Sorting'),
    ('matching', 'Matching'),
    ('slider', 'Slider'),
    ('image_reveal', 'Image Reveal'),
    ('layered_content', 'Layered Content'),
]

QUESTION_TYPE_CHOICES = [
    ('single_choice', 'Single Choice'),
    ('multiple_select', 'Multiple Select'),
    ('true_false', 'True/False'),
    ('fill_blank', 'Fill in the Blank'),
    ('matching', 'Matching'),
    ('ordering', 'Ordering'),
    ('short_answer', 'Short Answer'),
]

ENDING_TYPE_CHOICES = [
    ('success', 'Success'),
    ('failure', 'Failure'),
    ('neutral', 'Neutral'),
]


class AuthoringAsset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'organizations.Organization', on_delete=models.CASCADE,
        related_name='authoring_assets', db_index=True
    )
    file_hash = models.CharField(max_length=64, db_index=True)
    file = models.FileField(upload_to=org_asset_path)
    original_filename = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=100)
    file_size = models.BigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'authoring_asset'
        ordering = ['-created_at']

    def __str__(self):
        return f"Asset ({self.original_filename})"


class LessonBlockTree(models.Model):
    organization = models.ForeignKey(
        'organizations.Organization', on_delete=models.CASCADE,
        related_name='block_trees', db_index=True
    )
    lesson = models.OneToOneField(
        'courses.Lesson', on_delete=models.CASCADE,
        related_name='block_tree'
    )
    root_block_ids = models.JSONField(default=list, blank=True)
    version = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'authoring_lessonblocktree'

    def __str__(self):
        return f"BlockTree for Lesson {self.lesson_id} (v{self.version})"


class LessonBlock(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        'organizations.Organization', on_delete=models.CASCADE,
        related_name='lesson_blocks', db_index=True
    )
    tree = models.ForeignKey(
        LessonBlockTree, on_delete=models.CASCADE,
        related_name='blocks'
    )
    parent_block = models.ForeignKey(
        'self', on_delete=models.CASCADE, null=True, blank=True,
        related_name='children'
    )
    block_type = models.CharField(max_length=50, choices=BLOCK_TYPE_CHOICES)
    order = models.IntegerField(default=0, db_index=True)
    settings = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'authoring_lessonblock'
        ordering = ['order', 'created_at']

    def __str__(self):
        return f"Block [{self.block_type}] {self.id}"


class ReadingContent(models.Model):
    block = models.OneToOneField(
        LessonBlock, on_delete=models.CASCADE,
        related_name='reading_payload'
    )
    html_content = models.TextField(blank=True, default='')
    markdown_content = models.TextField(blank=True, default='')
    meta_data = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'authoring_readingcontent'

    def __str__(self):
        return f"Reading Content for Block {self.block_id}"


class InteractionBlock(models.Model):
    block = models.OneToOneField(
        LessonBlock, on_delete=models.CASCADE,
        related_name='interaction_payload'
    )
    interaction_type = models.CharField(max_length=50, choices=INTERACTION_TYPE_CHOICES)
    config = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'authoring_interactionblock'

    def __str__(self):
        return f"Interaction [{self.interaction_type}] for Block {self.block_id}"


class KCQuestion(models.Model):
    block = models.ForeignKey(
        LessonBlock, on_delete=models.CASCADE,
        related_name='kc_questions'
    )
    organization = models.ForeignKey(
        'organizations.Organization', on_delete=models.CASCADE,
        related_name='kc_questions', db_index=True
    )
    question_type = models.CharField(max_length=30, choices=QUESTION_TYPE_CHOICES)
    prompt = models.TextField()
    choices = models.JSONField(default=list, blank=True)
    correct_feedback = models.TextField(blank=True, default='')
    incorrect_feedback = models.TextField(blank=True, default='')
    hint = models.TextField(blank=True, default='')
    points = models.IntegerField(default=1)
    order = models.IntegerField(default=0)

    class Meta:
        db_table = 'authoring_kc_question'
        ordering = ['order', 'id']

    def __str__(self):
        return f"KCQuestion ({self.question_type}) on Block {self.block_id}"


class ScenarioNode(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    block = models.ForeignKey(
        LessonBlock, on_delete=models.CASCADE,
        related_name='scenario_nodes'
    )
    title = models.CharField(max_length=255)
    content = models.TextField()
    media_url = models.CharField(max_length=1000, blank=True, default='')
    is_start_node = models.BooleanField(default=False)
    is_ending_node = models.BooleanField(default=False)
    ending_type = models.CharField(max_length=30, choices=ENDING_TYPE_CHOICES, null=True, blank=True)
    score_delta = models.IntegerField(default=0)
    choices = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = 'authoring_scenarionode'

    def __str__(self):
        return f"ScenarioNode [{self.title}] on Block {self.block_id}"


class CourseVersion(models.Model):
    organization = models.ForeignKey(
        'organizations.Organization', on_delete=models.CASCADE,
        related_name='course_versions', db_index=True
    )
    course = models.ForeignKey(
        'courses.Course', on_delete=models.CASCADE,
        related_name='versions'
    )
    version_number = models.IntegerField(default=1)
    manifest_snapshot = models.JSONField(default=dict)
    created_by = models.ForeignKey(
        'users.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_course_versions'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'authoring_courseversion'
        ordering = ['-version_number', '-created_at']

    def __str__(self):
        return f"Course {self.course_id} v{self.version_number}"
