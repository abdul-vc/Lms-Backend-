import sys
import subprocess
import shutil

def check_package(name):
    try:
        __import__(name)
        return True, "Installed"
    except ImportError:
        return False, "Missing"

def check_binary(cmd):
    path = shutil.which(cmd)
    return path is not None, path or "Not found on PATH"

def run_readiness():
    print("=== ENVIRONMENT READINESS CHECK FOR PHASE 5 ===")
    
    pip_packages = [
        ("python-pptx", "pptx"),
        ("pypdf", "pypdf"),
        ("python-docx", "docx"),
        ("mutagen", "mutagen"),
        ("beautifulsoup4", "bs4"),
        ("bleach", "bleach"),
        ("pdf2image", "pdf2image"),
        ("ffmpeg-python", "ffmpeg")
    ]

    print("\n1. Python Packages (pip):")
    all_pip_ok = True
    for pkg_name, import_name in pip_packages:
        ok, msg = check_package(import_name)
        print(f"  - {pkg_name:20s}: [{'OK' if ok else 'MISSING'}] {msg}")
        if not ok:
            all_pip_ok = False

    print("\n2. System Binary Diagnostics (PATH):")
    poppler_ok, poppler_path = check_binary("pdftoppm")
    print(f"  - Poppler (pdftoppm): [{'OK' if poppler_ok else 'MISSING'}] {poppler_path}")

    ffmpeg_ok, ffmpeg_path = check_binary("ffmpeg")
    print(f"  - FFmpeg (ffmpeg)   : [{'OK' if ffmpeg_ok else 'MISSING'}] {ffmpeg_path}")

    print("\n=== SUMMARY ===")
    if poppler_ok and ffmpeg_ok and all_pip_ok:
        print("ALL READINESS CHECKS PASSED. Ready for Phase 5.")
    else:
        print("SOME DEPENDENCIES ARE MISSING.")

if __name__ == '__main__':
    run_readiness()
