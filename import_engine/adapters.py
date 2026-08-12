import os
import re
import uuid
import hashlib
import zipfile
import tempfile
from io import BytesIO
from django.db import transaction
from django.core.files.base import ContentFile

import pptx
import pypdf
import docx
from bs4 import BeautifulSoup
import mutagen
import pdf2image

from authoring_engine.models import (
    AuthoringAsset, LessonBlockTree, LessonBlock,
    ReadingContent, InteractionBlock, KCQuestion, ScenarioNode
)
from courses.models import Course, Module, Lesson
import json
import shutil
from django.conf import settings
from courses.scorm_engine import parse_imsmanifest

class ImportAdapterException(Exception):
    pass


class BaseAdapter:
    def __init__(self, file_path, organization, user, target_course=None):
        self.file_path = file_path
        self.organization = organization
        self.user = user
        self.target_course = target_course
        self.warnings = []
        self.errors = []

    def parse(self):
        """Returns intermediate AST: { 'title': '...', 'modules': [ { 'title': '...', 'lessons': [ ... ] } ] }"""
        raise NotImplementedError


class PPTXAdapter(BaseAdapter):
    def parse(self):
        try:
            prs = pptx.Presentation(self.file_path)
        except Exception as e:
            raise ImportAdapterException(f"Failed to open PPTX file: {str(e)}")

        total_slides = len(prs.slides)
        if total_slides == 0:
            raise ImportAdapterException("PPTX presentation contains no slides.")

        failed_slides = 0
        lessons = []

        for idx, slide in enumerate(prs.slides, start=1):
            try:
                slide_title = f"Slide {idx}"
                blocks = []
                
                # Search for slide title shape
                for shape in slide.shapes:
                    if shape.has_text_frame and shape.text.strip():
                        if shape == slide.shapes.title or not blocks:
                            slide_title = shape.text.strip().split('\n')[0]
                            blocks.append({
                                'type': 'heading',
                                'payload': {'html': f"<h2>{slide_title}</h2>", 'markdown': slide_title}
                            })
                        else:
                            text_content = shape.text.strip()
                            if text_content:
                                blocks.append({
                                    'type': 'paragraph',
                                    'payload': {'html': f"<p>{text_content}</p>", 'markdown': text_content}
                                })

                if not blocks:
                    blocks.append({
                        'type': 'paragraph',
                        'payload': {'html': f"<p>Slide {idx} Content</p>", 'markdown': f"Slide {idx} Content"}
                    })

                lessons.append({
                    'title': slide_title,
                    'type': 'reading',
                    'duration': '5 min',
                    'blocks': blocks
                })

            except Exception as slide_err:
                failed_slides += 1
                self.warnings.append(f"Slide {idx} parsing warning: {str(slide_err)}")
                lessons.append({
                    'title': f"Slide {idx} (Conversion Warning)",
                    'type': 'reading',
                    'duration': '5 min',
                    'blocks': [{
                        'type': 'callout',
                        'payload': {
                            'html': f"<p><strong>Warning:</strong> Content on Slide {idx} could not be automatically converted.</p>",
                            'markdown': f"Warning: Content on Slide {idx} could not be automatically converted."
                        }
                    }]
                })

        # Check section 4.3 rollback threshold (>30% failure)
        failure_rate = (failed_slides / total_slides) * 100
        if failure_rate > 30.0:
            raise ImportAdapterException(f"Import failed: {failure_rate:.1f}% of slides failed parsing (>30% threshold).")

        main_title = os.path.basename(self.file_path).replace('.pptx', '').replace('_', ' ').title()
        return {
            'title': main_title,
            'modules': [
                {
                    'title': 'Module 1: Presentation Slides',
                    'summary': f'Imported from {os.path.basename(self.file_path)}',
                    'lessons': lessons
                }
            ]
        }


class PDFAdapter(BaseAdapter):
    def parse(self):
        try:
            reader = pypdf.PdfReader(self.file_path)
        except Exception as e:
            raise ImportAdapterException(f"Failed to open PDF file: {str(e)}")

        total_pages = len(reader.pages)
        if total_pages == 0:
            raise ImportAdapterException("PDF document contains no pages.")

        failed_pages = 0
        lessons = []

        for idx, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ''
                text = text.strip()

                lines = [line.strip() for line in text.split('\n') if line.strip()]
                page_title = lines[0] if lines else f"Page {idx}"
                body_text = "\n\n".join(lines[1:]) if len(lines) > 1 else text

                blocks = [
                    {'type': 'heading', 'payload': {'html': f"<h2>{page_title}</h2>", 'markdown': page_title}},
                    {'type': 'paragraph', 'payload': {'html': f"<p>{body_text or 'Document Page'}</p>", 'markdown': body_text or 'Document Page'}}
                ]

                lessons.append({
                    'title': page_title[:200],
                    'type': 'reading',
                    'duration': '5 min',
                    'blocks': blocks
                })

            except Exception as page_err:
                failed_pages += 1
                self.warnings.append(f"Page {idx} warning: {str(page_err)}")
                lessons.append({
                    'title': f"Page {idx} (Warning)",
                    'type': 'reading',
                    'duration': '5 min',
                    'blocks': [{
                        'type': 'callout',
                        'payload': {'html': f"<p>Warning: Page {idx} content could not be parsed.</p>", 'markdown': f"Warning: Page {idx} content could not be parsed."}
                    }]
                })

        failure_rate = (failed_pages / total_pages) * 100
        if failure_rate > 30.0:
            raise ImportAdapterException(f"Import failed: {failure_rate:.1f}% of pages failed parsing (>30% threshold).")

        main_title = os.path.basename(self.file_path).replace('.pdf', '').replace('_', ' ').title()
        return {
            'title': main_title,
            'modules': [
                {
                    'title': 'Module 1: Document Chapters',
                    'summary': f'Imported from {os.path.basename(self.file_path)}',
                    'lessons': lessons
                }
            ]
        }


class DOCXAdapter(BaseAdapter):
    def parse(self):
        try:
            doc = docx.Document(self.file_path)
        except Exception as e:
            raise ImportAdapterException(f"Failed to open DOCX document: {str(e)}")

        modules = []
        current_module = {'title': 'Module 1: General Content', 'summary': 'Docx import', 'lessons': []}
        current_lesson = {'title': 'Introduction', 'type': 'reading', 'duration': '5 min', 'blocks': []}

        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue

            style_name = para.style.name.lower() if para.style else ''
            if 'heading 1' in style_name:
                if current_lesson['blocks']:
                    current_module['lessons'].append(current_lesson)
                    current_lesson = {'title': text, 'type': 'reading', 'duration': '5 min', 'blocks': []}
                if current_module['lessons']:
                    modules.append(current_module)
                    current_module = {'title': text, 'summary': '', 'lessons': []}
            elif 'heading 2' in style_name:
                if current_lesson['blocks']:
                    current_module['lessons'].append(current_lesson)
                current_lesson = {'title': text, 'type': 'reading', 'duration': '5 min', 'blocks': []}
            else:
                current_lesson['blocks'].append({
                    'type': 'paragraph',
                    'payload': {'html': f"<p>{text}</p>", 'markdown': text}
                })

        if current_lesson['blocks'] or not current_module['lessons']:
            if not current_lesson['blocks']:
                current_lesson['blocks'].append({'type': 'paragraph', 'payload': {'html': '<p>Content</p>', 'markdown': 'Content'}})
            current_module['lessons'].append(current_lesson)
        if current_module['lessons']:
            modules.append(current_module)

        main_title = os.path.basename(self.file_path).replace('.docx', '').replace('_', ' ').title()
        return {
            'title': main_title,
            'modules': modules
        }


class VideoAdapter(BaseAdapter):
    def parse(self):
        rel_url = f"/media/import_scratch/{os.path.basename(self.file_path)}"
        main_title = os.path.basename(self.file_path).rsplit('.', 1)[0].replace('_', ' ').title()

        return {
            'title': main_title,
            'modules': [
                {
                    'title': 'Module 1: Video Content',
                    'summary': 'Imported video lesson',
                    'lessons': [
                        {
                            'title': main_title,
                            'type': 'video',
                            'duration': '10 min',
                            'video_url': rel_url,
                            'blocks': []
                        }
                    ]
                }
            ]
        }


class AudioAdapter(BaseAdapter):
    def parse(self):
        rel_url = f"/media/import_scratch/{os.path.basename(self.file_path)}"
        main_title = os.path.basename(self.file_path).rsplit('.', 1)[0].replace('_', ' ').title()

        return {
            'title': main_title,
            'modules': [
                {
                    'title': 'Module 1: Audio Content',
                    'summary': 'Imported audio lesson',
                    'lessons': [
                        {
                            'title': main_title,
                            'type': 'reading',
                            'duration': '5 min',
                            'blocks': [
                                {
                                    'type': 'audio',
                                    'payload': {
                                        'html': f'<audio controls src="{rel_url}"></audio>',
                                        'markdown': f'[Audio Track]({rel_url})'
                                    }
                                }
                            ]
                        }
                    ]
                }
            ]
        }


class HTMLZipAdapter(BaseAdapter):
    def parse(self):
        if not zipfile.is_zipfile(self.file_path):
            raise ImportAdapterException("File is not a valid ZIP archive.")

        with zipfile.ZipFile(self.file_path, 'r') as zf:
            namelist = zf.namelist()
            html_files = [f for f in namelist if f.endswith('.html') or f.endswith('.htm')]
            if not html_files:
                raise ImportAdapterException("ZIP archive contains no HTML files.")

            index_file = 'index.html' if 'index.html' in html_files else html_files[0]
            with zf.open(index_file) as f:
                soup = BeautifulSoup(f.read().decode('utf-8', errors='ignore'), 'html.parser')

            title = soup.title.string.strip() if soup.title and soup.title.string else 'HTML Package'
            blocks = []
            for tag in soup.find_all(['h1', 'h2', 'h3', 'p', 'table']):
                if tag.name.startswith('h'):
                    blocks.append({'type': 'heading', 'payload': {'html': str(tag), 'markdown': tag.text.strip()}})
                elif tag.name == 'p':
                    blocks.append({'type': 'paragraph', 'payload': {'html': str(tag), 'markdown': tag.text.strip()}})
                elif tag.name == 'table':
                    blocks.append({'type': 'table', 'payload': {'html': str(tag), 'markdown': tag.text.strip()}})

            if not blocks:
                blocks.append({'type': 'paragraph', 'payload': {'html': '<p>HTML Content</p>', 'markdown': 'HTML Content'}})

            return {
                'title': title,
                'modules': [
                    {
                        'title': 'Module 1: Web Content',
                        'summary': f'Extracted from {index_file}',
                        'lessons': [
                            {'title': title, 'type': 'reading', 'duration': '5 min', 'blocks': blocks}
                        ]
                    }
                ]
            }


class SCORMAdapter(BaseAdapter):
    def parse(self):
        if not zipfile.is_zipfile(self.file_path):
            raise ImportAdapterException("Uploaded file is not a valid ZIP package.")

        temp_dir = tempfile.mkdtemp()
        with zipfile.ZipFile(self.file_path, 'r') as zf:
            zf.extractall(temp_dir)

        # Priority 1: Check for native LMS manifest snapshot
        manifest_json_path = None
        for cand in ['lams_manifest.json', 'course_manifest.json']:
            cand_p = os.path.join(temp_dir, cand)
            if os.path.exists(cand_p):
                manifest_json_path = cand_p
                break

        if manifest_json_path:
            with open(manifest_json_path, 'r', encoding='utf-8') as f:
                c_data = json.load(f)

            c_meta = c_data.get('metadata', {})
            course_title = c_meta.get('title') or c_data.get('title') or 'Imported SCORM Course'

            modules = []
            for m_idx, m_in in enumerate(c_data.get('modules', []), start=1):
                mod_title = m_in.get('title') or f"Module {m_idx}"
                mod_summary = m_in.get('summary', '')
                lessons = []

                for l_idx, l_in in enumerate(m_in.get('lessons', []), start=1):
                    les_type = l_in.get('type', 'reading')
                    v_url = l_in.get('video_url')
                    v_rel = l_in.get('video_rel_path') or v_url

                    new_video_url = None
                    if v_rel and not str(v_rel).startswith(('http://', 'https://')):
                        clean_rel = str(v_rel).lstrip('/\\')
                        for pfx in ['api/media/', 'media/', '/api/media/', '/media/']:
                            if clean_rel.startswith(pfx):
                                clean_rel = clean_rel[len(pfx):]
                                break

                        src_on_disk = os.path.join(temp_dir, clean_rel)
                        if not os.path.exists(src_on_disk):
                            src_on_disk = os.path.join(temp_dir, 'media', clean_rel)

                        if os.path.exists(src_on_disk) and os.path.isfile(src_on_disk):
                            ext = os.path.splitext(src_on_disk)[1] or '.mp4'
                            dest_filename = f"{uuid.uuid4().hex}{ext}"
                            dest_dir = os.path.join(settings.MEDIA_ROOT, 'course_videos')
                            os.makedirs(dest_dir, exist_ok=True)
                            dest_path = os.path.join(dest_dir, dest_filename)
                            shutil.copy2(src_on_disk, dest_path)
                            new_video_url = f"/api/media/course_videos/{dest_filename}"
                    elif v_url and str(v_url).startswith(('http://', 'https://')):
                        new_video_url = str(v_url)

                    lessons.append({
                        'title': l_in.get('title') or f"Lesson {l_idx}",
                        'type': les_type,
                        'duration': l_in.get('duration', '5 min'),
                        'order': l_in.get('order', l_idx),
                        'video_url': new_video_url,
                        'interaction': l_in.get('interaction'),
                        'content_tree': l_in.get('content_tree'),
                        'blocks': l_in.get('blocks', [])
                    })

                modules.append({
                    'title': mod_title,
                    'summary': mod_summary,
                    'order': m_in.get('order', m_idx),
                    'lessons': lessons
                })

            return {
                'title': course_title,
                'modules': modules
            }

        # Priority 2: Generic SCORM package (imsmanifest.xml)
        target_xml = os.path.join(temp_dir, 'imsmanifest.xml')
        if not os.path.exists(target_xml):
            raise ImportAdapterException("imsmanifest.xml not found in SCORM ZIP package.")

        manifest_data = parse_imsmanifest(target_xml)
        course_title = manifest_data.get('title') or 'SCORM Package'
        parsed_modules = manifest_data.get('modules', [])

        if not parsed_modules:
            sco_items = manifest_data.get('sco_items', [])
            parsed_modules = [{
                'title': 'Module 1',
                'lessons': sco_items
            }]

        modules = []
        for m_idx, m_in in enumerate(parsed_modules, start=1):
            mod_title = m_in.get('title') or f"Module {m_idx}"
            lessons = []

            for l_idx, l_in in enumerate(m_in.get('lessons', []), start=1):
                les_title = l_in.get('title') or f"Lesson {l_idx}"
                href = l_in.get('launch_href', '')
                explicit_type = l_in.get('type')

                les_type = 'reading'
                new_video_url = None

                ext = os.path.splitext(href)[1].lower() if href else ''
                is_video_href = ext in ['.mp4', '.m4v', '.webm', '.ogv', '.mov', '.avi'] or 'video' in href.lower() or explicit_type == 'video'

                target_video_file = None
                if href and os.path.exists(os.path.join(temp_dir, href)) and ext in ['.mp4', '.m4v', '.webm', '.ogv', '.mov', '.avi']:
                    target_video_file = os.path.join(temp_dir, href)
                elif is_video_href:
                    for root_d, dirs_d, files_d in os.walk(temp_dir):
                        for f_d in files_d:
                            if f_d.lower().endswith(('.mp4', '.m4v', '.webm', '.mov', '.avi')):
                                target_video_file = os.path.join(root_d, f_d)
                                break
                        if target_video_file:
                            break

                if target_video_file:
                    v_ext = os.path.splitext(target_video_file)[1] or '.mp4'
                    dest_filename = f"{uuid.uuid4().hex}{v_ext}"
                    dest_dir = os.path.join(settings.MEDIA_ROOT, 'course_videos')
                    os.makedirs(dest_dir, exist_ok=True)
                    dest_path = os.path.join(dest_dir, dest_filename)
                    shutil.copy2(target_video_file, dest_path)
                    new_video_url = f"/api/media/course_videos/{dest_filename}"
                    les_type = 'video'
                elif explicit_type in ['video', 'reading', 'interactive', 'knowledge_check', 'scenario']:
                    les_type = explicit_type
                elif any(k in les_title.lower() or k in href.lower() for k in ['quiz', 'test', 'assessment', 'exam']):
                    les_type = 'knowledge_check'
                elif any(k in les_title.lower() or k in href.lower() for k in ['scenario', 'simulation', 'decision']):
                    les_type = 'scenario'
                elif any(k in les_title.lower() or k in href.lower() for k in ['interactive', 'activity']):
                    les_type = 'interactive'
                else:
                    les_type = 'reading'

                lessons.append({
                    'title': les_title,
                    'type': les_type,
                    'duration': '10 min',
                    'order': l_idx,
                    'video_url': new_video_url,
                    'blocks': [{
                        'type': 'paragraph',
                        'payload': {'html': f'<p>{les_title}</p>', 'markdown': les_title}
                    }]
                })

            modules.append({
                'title': mod_title,
                'order': m_idx,
                'lessons': lessons
            })

        return {
            'title': course_title,
            'modules': modules
        }
