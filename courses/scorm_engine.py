import os
import zipfile
import shutil
import xml.etree.ElementTree as ET
from django.conf import settings
from django.utils import timezone
from .models import Course, ScormPackage

def parse_imsmanifest(manifest_path):
    """
    Parses an imsmanifest.xml file to extract SCORM version, title, launch file,
    mastery score, and SCO items hierarchy.
    """
    if not os.path.exists(manifest_path):
        raise ValueError("imsmanifest.xml not found in the package root.")

    try:
        tree = ET.parse(manifest_path)
        root = tree.getroot()
    except Exception as e:
        raise ValueError(f"Failed to parse imsmanifest.xml XML: {str(e)}")

    # Remove XML namespaces for easier XPath querying
    for elem in root.iter():
        if '}' in elem.tag:
            elem.tag = elem.tag.split('}', 1)[1]

    # 1. Determine SCORM Version
    schema_version_elem = root.find('.//schemaversion')
    schema_version = schema_version_elem.text.strip() if schema_version_elem is not None and schema_version_elem.text else ''
    
    version = '1.2'
    if '2004' in schema_version or 'CAM 1.3' in schema_version:
        version = '2004'
    elif '1.2' in schema_version:
        version = '1.2'
    else:
        # Fallback inspection of root attributes
        root_str = ET.tostring(root, encoding='utf-8').decode('utf-8')
        if '2004' in root_str:
            version = '2004'

    # 2. Extract Course Title
    title_elem = root.find('.//organization/title') or root.find('.//title')
    title = title_elem.text.strip() if title_elem is not None and title_elem.text else ''

    # 3. Extract Mastery Score / Passing Score
    mastery_score = None
    mastery_elem = root.find('.//masteryscore') or root.find('.//minNormalizedMeasure')
    if mastery_elem is not None and mastery_elem.text:
        try:
            val = float(mastery_elem.text.strip())
            mastery_score = val * 100 if val <= 1.0 else val
        except ValueError:
            pass

    # 4. Extract Resources & Launch File (SCO)
    resources = {}
    default_launch = None
    for res in root.findall('.//resource'):
        identifier = res.get('identifier')
        href = res.get('href')
        type_attr = res.get('type', '')
        scorm_type = res.get('scormtype', res.get('scormType', '')).lower()

        if identifier and href:
            resources[identifier] = {
                'href': href,
                'type': type_attr,
                'scorm_type': scorm_type
            }
            if not default_launch and (scorm_type == 'sco' or 'html' in href.lower()):
                default_launch = href

    # 5. Extract SCO Items Tree
    sco_items = []
    for item in root.findall('.//item'):
        item_id = item.get('identifier')
        ref = item.get('identifierref')
        item_title_elem = item.find('title')
        item_title = item_title_elem.text.strip() if item_title_elem is not None and item_title_elem.text else ''
        
        launch_href = resources.get(ref, {}).get('href', '') if ref else ''
        if launch_href and not default_launch:
            default_launch = launch_href

        sco_items.append({
            'identifier': item_id,
            'title': item_title,
            'launch_href': launch_href
        })

    # If launch file was not explicitly found in items/resources, check common default filenames
    if not default_launch and resources:
        first_res = list(resources.values())[0]
        default_launch = first_res['href']

    with open(manifest_path, 'r', encoding='utf-8', errors='ignore') as f:
        raw_manifest_xml = f.read()

    return {
        'version': version,
        'schema_version': schema_version or version,
        'title': title,
        'mastery_score': mastery_score,
        'launch_file': default_launch,
        'sco_items': sco_items,
        'raw_manifest_xml': raw_manifest_xml,
    }


