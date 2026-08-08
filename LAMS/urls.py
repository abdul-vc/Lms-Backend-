"""
URL configuration for LAMS project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
import os
import mimetypes
from django.contrib import admin
from django.urls import path, include
from django.http import StreamingHttpResponse, HttpResponse, Http404
from django.conf import settings
from django.conf.urls.static import static

# Force autodiscover and import all app admin modules
import users.admin
import organizations.admin
import master_setup.admin
import courses.admin
import authoring_engine.admin
import import_engine.admin
admin.autodiscover()



def stream_video_file(request, file_path):
    import os
    import re
    from django.http import StreamingHttpResponse, Http404, HttpResponse

    if not os.path.exists(file_path):
        raise Http404(f"Video file missing on disk: {file_path}")

    file_size = os.path.getsize(file_path)
    range_header = request.META.get('HTTP_RANGE', '').strip()
    
    if range_header.startswith('bytes='):
        # Parse range e.g. "bytes=0-999"
        range_val = range_header[6:]
        start_str, _, end_str = range_val.partition('-')
        start = int(start_str) if start_str else 0
        end = int(end_str) if end_str else file_size - 1
        end = min(end, file_size - 1)
        length = end - start + 1

        def file_iterator(path, offset, chunk_size):
            with open(path, 'rb') as f:
                f.seek(offset)
                remaining = chunk_size
                while remaining > 0:
                    data = f.read(min(65536, remaining))
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        response = StreamingHttpResponse(
            file_iterator(file_path, start, length),
            status=206,
            content_type='video/mp4',
        )
        response['Content-Range'] = f'bytes {start}-{end}/{file_size}'
        response['Content-Length'] = length
    else:
        def full_file_iterator(path):
            with open(path, 'rb') as f:
                while True:
                    data = f.read(65536)
                    if not data:
                        break
                    yield data
                    
        response = StreamingHttpResponse(
            full_file_iterator(file_path),
            content_type='video/mp4',
        )
        response['Content-Length'] = file_size

    response['Accept-Ranges'] = 'bytes'
    return response




def serve_scorm_media(request, path):
    """
    Custom view to serve SCORM package files with correct MIME types,
    CORS headers, and no frame-busting headers.
    """
    file_path = os.path.join(settings.MEDIA_ROOT, 'scorm', path)
    if not os.path.exists(file_path) or os.path.isdir(file_path):
        raise Http404(f"SCORM file not found on disk: {file_path}")

    content_type, encoding = mimetypes.guess_type(file_path)
    content_type = content_type or 'application/octet-stream'

    with open(file_path, 'rb') as f:
        content = f.read()

    # If serving HTML launch file, inject a cross-origin safe SCORM API locator wrapper
    if content_type == 'text/html' and isinstance(content, bytes):
        html_str = content.decode('utf-8', errors='ignore')
        bridge_script = """<script>
(function() {
  function findScormApi12() {
    try { if (window.parent && window.parent.API) return window.parent.API; } catch(e) {}
    try { if (window.top && window.top.API) return window.top.API; } catch(e) {}
    return null;
  }
  function findScormApi2004() {
    try { if (window.parent && window.parent.API_1484_11) return window.parent.API_1484_11; } catch(e) {}
    try { if (window.top && window.top.API_1484_11) return window.top.API_1484_11; } catch(e) {}
    return null;
  }
  window.API = window.API || findScormApi12();
  window.API_1484_11 = window.API_1484_11 || findScormApi2004();
})();
</script>"""
        if '</head>' in html_str:
            html_str = html_str.replace('</head>', f'{bridge_script}</head>', 1)
        elif '<body>' in html_str:
            html_str = html_str.replace('<body>', f'<body>{bridge_script}', 1)
        else:
            html_str = bridge_script + html_str
        content = html_str.encode('utf-8')

    response = HttpResponse(content, content_type=content_type)
    if encoding:
        response['Content-Encoding'] = encoding

    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    response['Access-Control-Allow-Headers'] = '*'
    if 'X-Frame-Options' in response:
        del response['X-Frame-Options']
    return response


def serve_media_video(request, path):
    """
    Custom video streaming view for videos uploaded to MEDIA_ROOT/course_videos/.
    """
    file_path = os.path.join(settings.MEDIA_ROOT, 'course_videos', path)
    return stream_video_file(request, file_path)


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/users/', include('users.urls')),
    path('api/', include('organizations.urls')),
    path('api/', include('courses.urls')),
    path('api/', include('master_setup.urls')),
    path('api/', include('authoring_engine.urls')),
    path('api/', include('import_engine.urls')),
    path('api/', include('scorm_export.urls')),
    # Serve uploaded SCORM packages and videos directly with CORS & frame support
    path('media/scorm/<path:path>', serve_scorm_media, name='serve_scorm_media'),
    path('media/course_videos/<path:path>', serve_media_video, name='serve_media_video'),
]

# Serve remaining uploaded media files (hero images, logos) in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
