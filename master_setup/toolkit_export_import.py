"""
Toolkit Export & Import Engine
Exports and imports Toolkit categories, articles, change logs, and configurations in JSON and ZIP backup formats.
"""
import json
import zipfile
import io
from django.utils import timezone

def export_toolkit_data(category_ids=None):
    from master_setup.models import (
        ToolkitCategory, ToolkitArticle, ToolkitChangeLog, ToolkitReleaseNote
    )

    cats_qs = ToolkitCategory.objects.all()
    if category_ids:
        cats_qs = cats_qs.filter(id__in=category_ids)

    categories_data = []
    for cat in cats_qs:
        articles_data = []
        for art in cat.articles.all():
            articles_data.append({
                'title': art.title,
                'slug': art.slug,
                'summary': art.summary,
                'content': art.content,
                'status': art.status,
                'version': art.version,
                'error_code': art.error_code,
                'tags': art.tags,
                'created_at': art.created_at.isoformat() if art.created_at else None,
                'updated_at': art.updated_at.isoformat() if art.updated_at else None,
            })
        categories_data.append({
            'name': cat.name,
            'slug': cat.slug,
            'icon': cat.icon,
            'description': cat.description,
            'order': cat.order,
            'articles': articles_data
        })

    changelogs_data = list(ToolkitChangeLog.objects.values())
    releasenotes_data = list(ToolkitReleaseNote.objects.values())

    export_pack = {
        'version': '2.4.0',
        'exported_at': timezone.now().isoformat(),
        'categories': categories_data,
        'changelogs': changelogs_data,
        'releasenotes': releasenotes_data
    }
    return export_pack


def import_toolkit_data(import_pack, user=None):
    from master_setup.models import (
        ToolkitCategory, ToolkitArticle, ToolkitArticleVersion, ToolkitAuditLog
    )

    imported_cats = 0
    imported_arts = 0

    for cat_data in import_pack.get('categories', []):
        cat, _ = ToolkitCategory.objects.get_or_create(
            slug=cat_data['slug'],
            defaults={
                'name': cat_data['name'],
                'icon': cat_data.get('icon', 'BookOpen'),
                'description': cat_data.get('description', ''),
                'order': cat_data.get('order', 0)
            }
        )
        imported_cats += 1

        for art_data in cat_data.get('articles', []):
            art, created = ToolkitArticle.objects.get_or_create(
                slug=art_data['slug'],
                defaults={
                    'category': cat,
                    'title': art_data['title'],
                    'summary': art_data.get('summary', ''),
                    'content': art_data.get('content', ''),
                    'status': art_data.get('status', 'draft'),
                    'version': art_data.get('version', 1),
                    'error_code': art_data.get('error_code'),
                    'tags': art_data.get('tags', []),
                    'created_by': user
                }
            )
            if not created:
                art.title = art_data['title']
                art.summary = art_data.get('summary', '')
                art.content = art_data.get('content', '')
                art.status = art_data.get('status', art.status)
                art.version += 1
                art.save()

            ToolkitArticleVersion.objects.create(
                article=art,
                version_number=art.version,
                title=art.title,
                summary=art.summary,
                content=art.content,
                created_by=user
            )
            imported_arts += 1

    ToolkitAuditLog.objects.create(
        action='IMPORT_PACK',
        category_name='Toolkit Import',
        performed_by=user,
        details={'imported_categories': imported_cats, 'imported_articles': imported_arts}
    )

    return {'imported_categories': imported_cats, 'imported_articles': imported_arts}
