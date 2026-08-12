import os
import bleach
from django.db import transaction
from .models import ImportJob
from .adapters import (
    PPTXAdapter, PDFAdapter, DOCXAdapter, VideoAdapter,
    AudioAdapter, HTMLZipAdapter, SCORMAdapter, ImportAdapterException
)
from courses.models import Course, Module, Lesson
from authoring_engine.models import (
    LessonBlockTree, LessonBlock, ReadingContent,
    InteractionBlock, KCQuestion, ScenarioNode, AuthoringAsset
)

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

def sanitize_html(html_str: str) -> str:
    if not html_str:
        return ''
    return bleach.clean(html_str, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES)

ADAPTER_MAP = {
    'pptx': PPTXAdapter,
    'pdf': PDFAdapter,
    'docx': DOCXAdapter,
    'video': VideoAdapter,
    'audio': AudioAdapter,
    'html': HTMLZipAdapter,
    'zip': HTMLZipAdapter,
    'scorm': SCORMAdapter,
}

def run_import_pipeline(import_job_id):
    """
    Executes the 5-stage Universal Import Engine pipeline synchronously.
    """
    job = ImportJob.objects.get(id=import_job_id)
    job.status = 'extracting'
    job.progress_percent = 10
    job.save(update_fields=['status', 'progress_percent'])

    try:
        # Stage 1 & 2: Parse & Adapt
        adapter_cls = ADAPTER_MAP.get(job.source_format)
        if not adapter_cls:
            raise ImportAdapterException(f"Unsupported format: {job.source_format}")

        file_path = job.source_file.path
        if not os.path.exists(file_path):
            raise ImportAdapterException(f"Source file missing on disk: {file_path}")

        job.status = 'parsing'
        job.progress_percent = 30
        job.save(update_fields=['status', 'progress_percent'])

        adapter = adapter_cls(file_path, job.organization, job.created_by, job.target_course)
        ast = adapter.parse()

        # Stage 3 & 4: Convert & Normalize
        job.status = 'converting'
        job.progress_percent = 50
        job.save(update_fields=['status', 'progress_percent'])

        if adapter.warnings:
            job.error_log = adapter.warnings
            job.save(update_fields=['error_log'])

        # Stage 5: Generate Internal Format within Atomic Transaction
        job.status = 'normalizing'
        job.progress_percent = 70
        job.save(update_fields=['status', 'progress_percent'])

        with transaction.atomic():
            # Get or create Course
            if job.target_course:
                course = job.target_course
            else:
                course = Course.objects.create(
                    organization=job.organization,
                    author=job.created_by,
                    title=ast.get('title') or 'Imported Course',
                    status='draft',
                    level='Foundational'
                )
                job.target_course = course
                job.save(update_fields=['target_course'])

            # Create Modules & Lessons
            modules_data = ast.get('modules', [])
            for m_idx, m_data in enumerate(modules_data, start=1):
                module = Module.objects.create(
                    course=course,
                    title=m_data.get('title') or f"Module {m_idx}",
                    summary=m_data.get('summary', ''),
                    order=m_idx
                )

                lessons_data = m_data.get('lessons', [])
                for l_idx, l_data in enumerate(lessons_data, start=1):
                    lesson = Lesson.objects.create(
                        module=module,
                        title=l_data.get('title') or f"Lesson {l_idx}",
                        type=l_data.get('type', 'reading'),
                        duration=l_data.get('duration', '5 min'),
                        order=l_idx,
                        video_url=l_data.get('video_url', None)
                    )

                    # For non-video lessons, create block tree and blocks
                    if lesson.type != 'video':
                        tree = LessonBlockTree.objects.create(
                            organization=job.organization,
                            lesson=lesson
                        )
                        c_tree = l_data.get('content_tree')
                        root_ids = []

                        if c_tree and isinstance(c_tree, dict) and 'blocks' in c_tree:
                            blocks_dict = c_tree.get('blocks', {})
                            for b_id, b_info in blocks_dict.items():
                                b_type = b_info.get('type', 'paragraph')
                                b_order = b_info.get('order', 0)
                                b_settings = b_info.get('settings', {'align': 'left', 'width': 'full'})
                                payload = b_info.get('payload', {})

                                block = LessonBlock.objects.create(
                                    organization=job.organization,
                                    tree=tree,
                                    block_type=b_type,
                                    order=b_order,
                                    settings=b_settings
                                )
                                root_ids.append(str(block.id))

                                if b_type in ['heading', 'paragraph', 'quote', 'code', 'callout', 'table', 'pdf']:
                                    raw_h = payload.get('html', '<p>Content</p>')
                                    clean_h = sanitize_html(raw_h)
                                    ReadingContent.objects.create(
                                        block=block,
                                        html_content=clean_h,
                                        markdown_content=payload.get('markdown', clean_h)
                                    )
                                elif b_type == 'interaction':
                                    InteractionBlock.objects.create(
                                        block=block,
                                        interaction_type=payload.get('interaction_type', 'hotspots'),
                                        config=payload.get('config', {})
                                    )
                                elif b_type == 'quiz' or 'questions' in payload:
                                    for q in payload.get('questions', []):
                                        KCQuestion.objects.create(
                                            organization=job.organization,
                                            block=block,
                                            prompt=q.get('prompt', 'Question'),
                                            question_type=q.get('type', 'single_choice'),
                                            choices=q.get('choices', []),
                                            points=q.get('points', 1)
                                        )
                                elif b_type == 'scenario' or 'nodes' in payload:
                                    for n in payload.get('nodes', []):
                                        ScenarioNode.objects.create(
                                            block=block,
                                            title=n.get('title', 'Scenario Node'),
                                            content=n.get('content', ''),
                                            is_start_node=n.get('is_start', False),
                                            is_ending_node=n.get('is_ending', False),
                                            ending_type=n.get('ending_type', 'neutral'),
                                            score_delta=n.get('score_delta', 0),
                                            choices=n.get('choices', [])
                                        )
                        else:
                            blocks_data = l_data.get('blocks', [])
                            for b_idx, b_data in enumerate(blocks_data):
                                b_type = b_data.get('type', 'paragraph')
                                block = LessonBlock.objects.create(
                                    organization=job.organization,
                                    tree=tree,
                                    block_type=b_type,
                                    order=b_idx,
                                    settings={'align': 'left', 'width': 'full'}
                                )
                                root_ids.append(str(block.id))

                                payload = b_data.get('payload', {})
                                if b_type in ['heading', 'paragraph', 'quote', 'code', 'callout', 'table', 'pdf']:
                                    raw_h = payload.get('html', '<p>Content</p>')
                                    clean_h = sanitize_html(raw_h)
                                    ReadingContent.objects.create(
                                        block=block,
                                        html_content=clean_h,
                                        markdown_content=payload.get('markdown', clean_h)
                                    )
                                elif b_type == 'interaction':
                                    InteractionBlock.objects.create(
                                        block=block,
                                        interaction_type=payload.get('interaction_type', 'hotspots'),
                                        config=payload.get('config', {})
                                    )

                        tree.root_block_ids = root_ids
                        tree.save(update_fields=['root_block_ids'])

        job.status = 'completed'
        job.progress_percent = 100
        job.save(update_fields=['status', 'progress_percent'])
        return True

    except Exception as e:
        job.status = 'failed'
        job.error_log.append(f"Fatal error: {str(e)}")
        job.save(update_fields=['status', 'error_log'])
        raise
