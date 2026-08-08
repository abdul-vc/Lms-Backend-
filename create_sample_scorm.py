import zipfile
import os

manifest_xml = """<?xml version="1.0" encoding="UTF-8"?>
<manifest identifier="sample_scorm_12" version="1.0" xmlns="http://www.imsproject.org/xsd/imscp_rootv1p1p2" xmlns:adlcp="http://www.adlnet.org/xsd/adlcp_rootv1p2" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.imsproject.org/xsd/imscp_rootv1p1p2 imscp_rootv1p1p2.xsd http://www.adlnet.org/xsd/adlcp_rootv1p2 adlcp_rootv1p2.xsd">
  <metadata>
    <schema>ADL SCORM</schema>
    <schemaversion>1.2</schemaversion>
  </metadata>
  <organizations default="org_sample">
    <organization identifier="org_sample">
      <title>Enterprise Multi-Tenant SCORM Demo</title>
      <item identifier="item_1" identifierref="res_1">
        <title>SCORM Interactive Module</title>
      </item>
    </organization>
  </organizations>
  <resources>
    <resource identifier="res_1" type="webcontent" adlcp:scormtype="sco" href="index.html">
      <file href="index.html" />
    </resource>
  </resources>
</manifest>
"""

index_html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>SCORM 1.2 Interactive Test</title>
  <style>
    body { font-family: system-ui, sans-serif; background: #0f172a; color: #f8fafc; padding: 40px; text-align: center; }
    .card { background: #1e293b; padding: 30px; rounded: 24px; max-width: 500px; margin: 0 auto; border: 1px solid #334155; border-radius: 16px; }
    button { background: #10b981; color: white; border: none; padding: 12px 24px; font-weight: bold; border-radius: 8px; cursor: pointer; margin-top: 20px; }
    button:hover { background: #059669; }
    .status { margin-top: 15px; font-size: 14px; color: #38bdf8; font-weight: bold; }
  </style>
</head>
<body>
  <div class="card">
    <h1>🚀 SCORM 1.2 Enterprise Test</h1>
    <p>This package communicates directly with the Django backend SCORM Runtime API.</p>
    <div id="status" class="status">Connecting to LMS SCORM API...</div>
    <button onclick="completeCourse()">Complete Course & Earn Certificate ✅</button>
  </div>

  <script>
    var API = null;
    function findAPI(win) {
      while (win.API == null && win.parent != null && win.parent != win) {
        win = win.parent;
      }
      return win.API;
    }

    window.onload = function() {
      API = findAPI(window);
      if (API) {
        API.LMSInitialize("");
        API.LMSSetValue("cmi.core.lesson_status", "incomplete");
        API.LMSCommit("");
        document.getElementById("status").innerText = "SCORM API Connected! Status: Incomplete";
      } else {
        document.getElementById("status").innerText = "Running standalone (No SCORM API found)";
      }
    };

    function completeCourse() {
      if (API) {
        API.LMSSetValue("cmi.core.lesson_status", "completed");
        API.LMSSetValue("cmi.core.score.raw", "100");
        API.LMSCommit("");
        API.LMSFinish("");
        document.getElementById("status").innerText = "🎉 Course Completed! Status: Completed (Score: 100%)";
      } else {
        alert("Completed!");
      }
    }
  </script>
</body>
</html>
"""

zip_filename = "sample_scorm_package.zip"
with zipfile.ZipFile(zip_filename, 'w') as z:
    z.writestr("imsmanifest.xml", manifest_xml)
    z.writestr("index.html", index_html)

print(f"Created {os.path.abspath(zip_filename)}")
