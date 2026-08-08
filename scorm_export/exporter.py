import os
import xml.etree.ElementTree as ET
import zipfile
import tempfile
import json
from io import BytesIO
from django.conf import settings
from courses.models import Course, Module, Lesson
from authoring_engine.publishing import compile_course_manifest

def generate_scorm_12_manifest(course, manifest_data):
    """
    Generates SCORM 1.2 imsmanifest.xml string.
    """
    title = course.title
    manifest_id = f"course_{course.id}_scorm12"

    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<manifest identifier="{manifest_id}" version="1.0"',
        '  xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2"',
        '  xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2"',
        '  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">',
        '  <metadata>',
        '    <schema>ADL SCORM</schema>',
        '    <schemaversion>1.2</schemaversion>',
        '  </metadata>',
        '  <organizations default="org_1">',
        '    <organization identifier="org_1">',
        f'      <title>{title}</title>'
    ]

    item_idx = 1
    for mod in manifest_data.get('modules', []):
        xml_lines.append(f'      <item identifier="item_mod_{mod["module_id"]}" identifierref="res_{mod["module_id"]}">')
        xml_lines.append(f'        <title>{mod["title"]}</title>')
        for les in mod.get('lessons', []):
            xml_lines.append(f'        <item identifier="item_les_{les["lesson_id"]}" identifierref="res_{les["lesson_id"]}">')
            xml_lines.append(f'          <title>{les["title"]}</title>')
            xml_lines.append('        </item>')
            item_idx += 1
        xml_lines.append('      </item>')

    xml_lines.append('    </organization>')
    xml_lines.append('  </organizations>')
    xml_lines.append('  <resources>')

    for mod in manifest_data.get('modules', []):
        xml_lines.append(f'    <resource identifier="res_{mod["module_id"]}" type="webcontent" adlcp:scormtype="sco" href="index.html">')
        xml_lines.append('      <file href="index.html"/>')
        xml_lines.append('    </resource>')

    xml_lines.append('  </resources>')
    xml_lines.append('</manifest>')

    return "\n".join(xml_lines)


def generate_scorm_2004_manifest(course, manifest_data):
    """
    Generates SCORM 2004 4th Edition imsmanifest.xml string.
    """
    title = course.title
    manifest_id = f"course_{course.id}_scorm2004"

    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<manifest identifier="{manifest_id}" version="1.0"',
        '  xmlns="http://www.imsproject.org/xsd/imscp_v1p1"',
        '  xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_v1p3"',
        '  xmlns:imsss="http://www.imsglobal.org/xsd/imsss"',
        '  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">',
        '  <metadata>',
        '    <schema>ADL SCORM</schema>',
        '    <schemaversion>2004 4th Edition</schemaversion>',
        '  </metadata>',
        '  <organizations default="org_1">',
        '    <organization identifier="org_1">',
        f'      <title>{title}</title>'
    ]

    for mod in manifest_data.get('modules', []):
        xml_lines.append(f'      <item identifier="item_mod_{mod["module_id"]}" identifierref="res_{mod["module_id"]}">')
        xml_lines.append(f'        <title>{mod["title"]}</title>')
        xml_lines.append('        <imsss:sequencing><imsss:controlMode choice="true" flow="true"/></imsss:sequencing>')
        xml_lines.append('      </item>')

    xml_lines.append('    </organization>')
    xml_lines.append('  </organizations>')
    xml_lines.append('  <resources>')

    for mod in manifest_data.get('modules', []):
        xml_lines.append(f'    <resource identifier="res_{mod["module_id"]}" type="webcontent" adlcp:scormtype="sco" href="index.html">')
        xml_lines.append('      <file href="index.html"/>')
        xml_lines.append('    </resource>')

    xml_lines.append('  </resources>')
    xml_lines.append('</manifest>')

    return "\n".join(xml_lines)


def generate_standalone_html(course, manifest_data, scorm_version="1.2"):
    """
    Generates a self-contained HTML player file (index.html) with built-in SCORM API adapter.
    """
    manifest_json = json.dumps(manifest_data)
    is_2004 = scorm_version == "2004"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{course.title} - Standalone SCORM Player</title>
  <style>
    body {{ font-family: system-ui, -apple-system, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 20px; }}
    .header {{ background: #1e293b; padding: 20px; border-radius: 12px; border: 1px solid #334155; margin-bottom: 20px; }}
    .title {{ font-size: 24px; font-weight: bold; color: #10b981; margin: 0 0 10px 0; }}
    .card {{ background: #1e293b; padding: 20px; border-radius: 12px; border: 1px solid #334155; margin-bottom: 16px; }}
    .btn {{ background: #10b981; color: white; border: none; padding: 10px 20px; border-radius: 8px; font-weight: bold; cursor: pointer; }}
    .btn:hover {{ background: #059669; }}
    .status-badge {{ background: #3b82f6; color: white; padding: 4px 12px; border-radius: 9999px; font-size: 12px; font-weight: bold; float: right; }}
  </style>
</head>
<body>
  <div class="header">
    <span class="status-badge" id="scorm-status">SCORM {scorm_version} Active</span>
    <h1 class="title">{course.title}</h1>
    <p>{course.subtitle or 'Interactive SCORM Course'}</p>
  </div>

  <div id="content-area"></div>

  <div class="card" style="text-align: center;">
    <button class="btn" onclick="completeSCORM()">Complete SCORM Lesson & Save Progress ✅</button>
  </div>

  <script>
    var COURSE_DATA = {manifest_json};
    var isSCORM2004 = {str(is_2004).lower()};
    var apiHandle = null;

    function findAPI(win) {{
      var attempts = 0;
      while (win && attempts < 10) {{
        if (!isSCORM2004 && win.API) return win.API;
        if (isSCORM2004 && win.API_1484_11) return win.API_1484_11;
        if (win.parent && win.parent !== win) win = win.parent;
        else if (win.opener) win = win.opener;
        else break;
        attempts++;
      }}
      return null;
    }}

    function initSCORM() {{
      apiHandle = findAPI(window);
      if (apiHandle) {{
        if (isSCORM2004) {{
          apiHandle.Initialize("");
          apiHandle.SetValue("cmi.completion_status", "incomplete");
        }} else {{
          apiHandle.LMSInitialize("");
          apiHandle.LMSSetValue("cmi.core.lesson_status", "incomplete");
        }}
      }}
      renderCourse();
    }}

    function renderCourse() {{
      var area = document.getElementById("content-area");
      var html = "";
      COURSE_DATA.modules.forEach(function(m) {{
        html += '<div class="card"><h2>' + m.title + '</h2>';
        m.lessons.forEach(function(l) {{
          html += '<div style="margin-top: 12px; padding: 12px; background: #0f172a; border-radius: 8px;">';
          html += '<h3>' + l.title + ' (' + l.type + ')</h3>';
          html += '</div>';
        }});
        html += '</div>';
      }});
      area.innerHTML = html;
    }}

    function completeSCORM() {{
      if (apiHandle) {{
        if (isSCORM2004) {{
          apiHandle.SetValue("cmi.completion_status", "completed");
          apiHandle.SetValue("cmi.success_status", "passed");
          apiHandle.Commit("");
          apiHandle.Terminate("");
        }} else {{
          apiHandle.LMSSetValue("cmi.core.lesson_status", "completed");
          apiHandle.LMSCommit("");
          apiHandle.LMSFinish("");
        }}
      }}
      alert("Lesson progress saved to SCORM LMS!");
    }}

    window.onload = initSCORM;
  </script>
</body>
</html>
"""


def export_course_to_scorm(course, scorm_version="1.2"):
    """
    Bundles manifest XML, index.html, and media assets into a zip byte stream.
    """
    manifest_data = compile_course_manifest(course)

    if scorm_version == "2004":
        manifest_xml = generate_scorm_2004_manifest(course, manifest_data)
    else:
        manifest_xml = generate_scorm_12_manifest(course, manifest_data)

    index_html = generate_standalone_html(course, manifest_data, scorm_version)

    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('imsmanifest.xml', manifest_xml)
        zf.writestr('index.html', index_html)

    zip_buffer.seek(0)
    return zip_buffer
