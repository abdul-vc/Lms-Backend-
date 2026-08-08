import bleach
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from organizations.permissions import IsOrgScoped
from organizations.audit import log_activity
from .models import (
    LessonBlockTree, LessonBlock, ReadingContent,
    InteractionBlock, KCQuestion, ScenarioNode, AuthoringAsset, CourseVersion
)
from .serializers import (
    LessonBlockTreeSerializer, LessonBlockSerializer, ReadingContentSerializer,
    InteractionBlockSerializer, KCQuestionSerializer, ScenarioNodeSerializer,
    AuthoringAssetSerializer, CourseVersionSerializer
)
from courses.models import Lesson

ALLOWED_TAGS = [
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'br', 'strong', 'em', 'u', 's',
    'blockquote', 'code', 'pre', 'ul', 'ol', 'li', 'table', 'thead', 'tbody',
    'tr', 'th', 'td', 'a', 'img', 'iframe', 'figure', 'figcaption', 'div', 'span'
]
ALLOWED_ATTRIBUTES = {
    'a': ['href', 'title', 'target', 'rel'],
    'img': ['src', 'alt', 'title', 'width', 'height', 'loading'],
    'iframe': ['src', 'width', 'height', 'frameborder', 'allowfullscreen'],
    '*': ['class', 'style', 'id', 'data-*']
}


def sanitize_html(raw_html: str) -> str:
    if not raw_html:
        return ''
    return bleach.clean(raw_html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES)


class LessonBlockTreeViewSet(viewsets.ModelViewSet):
    serializer_class = LessonBlockTreeSerializer
    permission_classes = [IsAuthenticated, IsOrgScoped]

    def get_queryset(self):
        if self.request.user.is_platform_super_admin:
            return LessonBlockTree.objects.all()
        return LessonBlockTree.objects.filter(organization_id=self.request.user.organization_id)


class LessonBlockViewSet(viewsets.ModelViewSet):
    serializer_class = LessonBlockSerializer
    permission_classes = [IsAuthenticated, IsOrgScoped]

    def get_queryset(self):
        if self.request.user.is_platform_super_admin:
            return LessonBlock.objects.all()
        return LessonBlock.objects.filter(organization_id=self.request.user.organization_id)

    def perform_create(self, serializer):
        tree = serializer.validated_data.get('tree')
        org = self.request.user.organization or (tree.organization if tree else None)
        block = serializer.save(organization=org)

        # 1. Update tree.root_block_ids if parent_block is None
        tree = block.tree
        if not block.parent_block:
            current_roots = list(tree.root_block_ids or [])
            if str(block.id) not in current_roots:
                current_roots.append(str(block.id))
                tree.root_block_ids = current_roots
                tree.save(update_fields=['root_block_ids', 'updated_at'])

        # 2. Instantiate default payloads per block_type
        bt = block.block_type
        if bt in ['heading', 'paragraph', 'quote', 'code', 'callout', 'table', 'pdf', 'image', 'video', 'audio']:
            default_meta = {'level': 'h2'} if bt == 'heading' else {}
            ReadingContent.objects.get_or_create(
                block=block,
                defaults={
                    'html_content': f'<{ "h2" if bt=="heading" else "p" }>New {bt.capitalize()} Block Content</{ "h2" if bt=="heading" else "p" }>',
                    'markdown_content': f'New {bt.capitalize()} Block Content',
                    'meta_data': default_meta
                }
            )
        elif bt == 'interaction':
            InteractionBlock.objects.get_or_create(
                block=block,
                defaults={
                    'interaction_type': 'hotspots',
                    'config': {}
                }
            )
        elif bt == 'quiz':
            KCQuestion.objects.get_or_create(
                block=block,
                organization=org,
                defaults={
                    'question_type': 'single_choice',
                    'prompt': 'Sample Knowledge Check Question',
                    'choices': [
                        {'id': 'c1', 'text': 'Option A', 'is_correct': True},
                        {'id': 'c2', 'text': 'Option B', 'is_correct': False}
                    ]
                }
            )
        elif bt == 'scenario':
            ScenarioNode.objects.get_or_create(
                block=block,
                defaults={
                    'title': 'Start Decision Point',
                    'content': 'Welcome to this interactive branching scenario.',
                    'is_start_node': True
                }
            )

    def perform_destroy(self, instance):
        tree = instance.tree
        block_id_str = str(instance.id)
        if tree.root_block_ids and block_id_str in tree.root_block_ids:
            tree.root_block_ids = [b for b in tree.root_block_ids if b != block_id_str]
            tree.save(update_fields=['root_block_ids', 'updated_at'])
        instance.delete()


class AuthoringAssetViewSet(viewsets.ModelViewSet):
    serializer_class = AuthoringAssetSerializer
    permission_classes = [IsAuthenticated, IsOrgScoped]

    def get_queryset(self):
        if self.request.user.is_platform_super_admin:
            return AuthoringAsset.objects.all()
        return AuthoringAsset.objects.filter(organization_id=self.request.user.organization_id)

    def perform_create(self, serializer):
        import hashlib
        uploaded_file = self.request.FILES.get('file')
        file_hash = ''
        if uploaded_file:
            hasher = hashlib.sha256()
            for chunk in uploaded_file.chunks():
                hasher.update(chunk)
            file_hash = hasher.hexdigest()

        org = self.request.user.organization
        serializer.save(
            organization=org,
            file_hash=file_hash,
            original_filename=uploaded_file.name if uploaded_file else '',
            mime_type=uploaded_file.content_type if uploaded_file else 'application/octet-stream',
            file_size=uploaded_file.size if uploaded_file else 0
        )


class ReadingContentViewSet(viewsets.ModelViewSet):
    serializer_class = ReadingContentSerializer
    permission_classes = [IsAuthenticated, IsOrgScoped]

    def get_queryset(self):
        if self.request.user.is_platform_super_admin:
            return ReadingContent.objects.all()
        return ReadingContent.objects.filter(block__organization_id=self.request.user.organization_id)

    def perform_create(self, serializer):
        html = serializer.validated_data.get('html_content', '')
        sanitized = sanitize_html(html)
        serializer.save(html_content=sanitized)

    def perform_update(self, serializer):
        html = serializer.validated_data.get('html_content', serializer.instance.html_content)
        sanitized = sanitize_html(html)
        serializer.save(html_content=sanitized)


class InteractionBlockViewSet(viewsets.ModelViewSet):
    serializer_class = InteractionBlockSerializer
    permission_classes = [IsAuthenticated, IsOrgScoped]

    def get_queryset(self):
        if self.request.user.is_platform_super_admin:
            return InteractionBlock.objects.all()
        return InteractionBlock.objects.filter(block__organization_id=self.request.user.organization_id)


class KCQuestionViewSet(viewsets.ModelViewSet):
    serializer_class = KCQuestionSerializer
    permission_classes = [IsAuthenticated, IsOrgScoped]

    def get_queryset(self):
        if self.request.user.is_platform_super_admin:
            return KCQuestion.objects.all()
        return KCQuestion.objects.filter(organization_id=self.request.user.organization_id)

    def perform_create(self, serializer):
        org = self.request.user.organization or serializer.validated_data['block'].organization
        serializer.save(organization=org)


class ScenarioNodeViewSet(viewsets.ModelViewSet):
    serializer_class = ScenarioNodeSerializer
    permission_classes = [IsAuthenticated, IsOrgScoped]

    def get_queryset(self):
        if self.request.user.is_platform_super_admin:
            return ScenarioNode.objects.all()
        return ScenarioNode.objects.filter(block__organization_id=self.request.user.organization_id)


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsOrgScoped])
def evaluate_kc_question(request, question_id):
    """
    Evaluation Engine for Knowledge Check (Section 9)
    Payload: { selected_choices: ["c1", ...], text_response: "...", attempt_number: 1 }
    """
    try:
        q = KCQuestion.objects.get(id=question_id)
    except KCQuestion.DoesNotExist:
        return Response({'detail': 'Question not found'}, status=status.HTTP_404_NOT_FOUND)

    selected = request.data.get('selected_choices', [])
    attempt_num = int(request.data.get('attempt_number', 1))

    is_correct = False
    if q.question_type in ['single_choice', 'true_false']:
        correct_ids = [c['id'] for c in q.choices if c.get('is_correct')]
        is_correct = len(selected) == 1 and selected[0] in correct_ids
    elif q.question_type == 'multiple_select':
        correct_ids = set(c['id'] for c in q.choices if c.get('is_correct'))
        is_correct = set(selected) == correct_ids
    elif q.question_type == 'fill_blank':
        text_val = str(request.data.get('text_response', '')).strip().lower()
        correct_answers = [str(c.get('text', '')).strip().lower() for c in q.choices if c.get('is_correct')]
        is_correct = text_val in correct_answers

    score_earned = q.points if is_correct else 0
    feedback = q.correct_feedback if is_correct else q.incorrect_feedback

    return Response({
        'question_id': q.id,
        'is_correct': is_correct,
        'score_earned': score_earned,
        'max_points': q.points,
        'feedback': feedback,
        'hint': q.hint if not is_correct and attempt_num < 3 else '',
        'attempt_number': attempt_num
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, IsOrgScoped])
def validate_scenario(request, block_id):
    """
    Validation Engine for Branching Scenario (Section 10)
    Checks: Exactly one Start Node, at least one Ending Node.
    """
    nodes = ScenarioNode.objects.filter(block_id=block_id)
    start_nodes = nodes.filter(is_start_node=True)
    ending_nodes = nodes.filter(is_ending_node=True)

    errors = []
    if start_nodes.count() != 1:
        errors.append(f"Scenario must have exactly 1 start node (found {start_nodes.count()}).")
    if ending_nodes.count() < 1:
        errors.append("Scenario must have at least 1 ending node.")

    is_valid = len(errors) == 0

    return Response({
        'block_id': str(block_id),
        'is_valid': is_valid,
        'total_nodes': nodes.count(),
        'start_node_id': str(start_nodes.first().id) if start_nodes.exists() else None,
        'ending_node_ids': [str(n.id) for n in ending_nodes],
        'errors': errors
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated, IsOrgScoped])
def reorder_blocks(request, tree_id):
    """
    POST /api/authoring/trees/{tree_id}/reorder/
    """
    try:
        tree = LessonBlockTree.objects.get(id=tree_id)
    except LessonBlockTree.DoesNotExist:
        return Response({'detail': 'Tree not found'}, status=status.HTTP_404_NOT_FOUND)

    if not request.user.is_platform_super_admin and tree.organization_id != request.user.organization_id:
        return Response({'detail': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)

    parent_id = request.data.get('parent_block_id')
    ordered_ids = request.data.get('ordered_block_ids', [])
    str_ids = [str(b_id) for b_id in ordered_ids]

    if parent_id is None:
        tree.root_block_ids = str_ids
        tree.save(update_fields=['root_block_ids', 'updated_at'])
    
    for idx, block_id in enumerate(str_ids):
        LessonBlock.objects.filter(id=block_id, tree=tree).update(order=idx, parent_block_id=parent_id)

    return Response({'status': 'reordered', 'tree_id': tree.id, 'ordered_block_ids': str_ids})


class CourseVersionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CourseVersionSerializer
    permission_classes = [IsAuthenticated, IsOrgScoped]

    def get_queryset(self):
        qs = CourseVersion.objects.all()
        if not self.request.user.is_platform_super_admin:
            qs = qs.filter(organization_id=self.request.user.organization_id)
        
        course_id = self.request.query_params.get('course')
        if course_id:
            qs = qs.filter(course_id=course_id)
        return qs.order_by('-version_number')

    from rest_framework.decorators import action
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsOrgScoped])
    def rollback(self, request, pk=None):
        version = self.get_object()
        course = version.course

        if not request.user.is_platform_super_admin and course.organization_id != request.user.organization_id:
            return Response({'detail': 'Access denied'}, status=status.HTTP_403_FORBIDDEN)

        # Restore course status to draft without destroying version history
        course.status = 'draft'
        meta = version.manifest_snapshot.get('metadata', {})
        if 'title' in meta:
            course.title = meta['title']
        if 'subtitle' in meta:
            course.subtitle = meta['subtitle']
        course.save(update_fields=['status', 'title', 'subtitle', 'updated_at'])

        log_activity(request, 'course_rolled_back', target=course, organization=course.organization)

        return Response({
            'status': 'Course restored to draft state from version snapshot',
            'version_number': version.version_number,
            'course_id': course.id
        })

