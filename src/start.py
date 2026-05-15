#!/usr/bin/env python3
"""
LaunchPad - Easy Launcher
Checks dependencies and starts the application
"""

import sys
import subprocess
from pathlib import Path

def check_dependency(package_name, import_name=None):
    """Check if a Python package is installed"""
    if import_name is None:
        import_name = package_name
    
    try:
        __import__(import_name)
        print(f"✓ {package_name} is installed")
        return True
    except ImportError:
        print(f"✗ {package_name} is NOT installed")
        return False

def main():
    print("="*60)
    print("  LaunchPad - LinkedIn Auto-Apply Bot")
    print("  Dependency Checker & Launcher")
    print("="*60)
    print()
    
    # Check Python version
    print("Checking Python version...")
    if sys.version_info < (3, 8):
        print(f"✗ Python 3.8+ required (you have {sys.version_info.major}.{sys.version_info.minor})")
        return
    else:
        print(f"✓ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    print()
    
    # Check required packages
    print("Checking Python packages...")
    required_packages = [
        ("flask", "flask"),
        ("flask-cors", "flask_cors"),
        ("playwright", "playwright"),
    ]
    
    missing = []
    for package, import_name in required_packages:
        if not check_dependency(package, import_name):
            missing.append(package)
    
    print()
    
    if missing:
        print("❌ Missing packages detected!")
        print()
        print("Install missing packages with:")
        print(f"  pip install {' '.join(missing)}")
        print()
        print("Then install Playwright browsers:")
        print("  playwright install chromium")
        return
    
    # Check Playwright browsers
    print("Checking Playwright browsers...")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
                browser.close()
                print("✓ Chromium browser is installed")
            except Exception:
                print("✗ Chromium browser NOT installed")
                print()
                print("Install with:")
                print("  playwright install chromium")
                return
    except Exception as e:
        print(f"✗ Error checking browsers: {e}")
        return
    
    print()
    
    # Check file structure
    print("Checking file structure...")
    base_dir = Path(__file__).parent
    
    required_files = {
        "api.py": "Backend API",
        "linkedin_bot_playwright.py": "Bot script",
        "index.html": "Frontend UI",
    }
    
    missing_files = []
    for filename, description in required_files.items():
        filepath = base_dir / filename
        if filepath.exists():
            print(f"✓ {description}: {filename}")
        else:
            print(f"✗ {description}: {filename} NOT FOUND")
            missing_files.append(filename)
    
    print()
    
    # Create data directories
    data_dir = base_dir / "data"
    input_dir = data_dir / "input"
    output_dir = data_dir / "output"
    
    for directory in [data_dir, input_dir, output_dir]:
        directory.mkdir(parents=True, exist_ok=True)
        print(f"✓ Directory: {directory.relative_to(base_dir)}")
    
    print()
    
    if missing_files:
        print("❌ Missing required files!")
        print()
        print("Please ensure these files are in the same directory:")
        for f in missing_files:
            print(f"  - {f}")
        return
    
    # All checks passed
    print("="*60)
    print("✅ All checks passed!")
    print("="*60)
    print()
    print("Starting LaunchPad server...")
    print()
    print("📍 Server will be available at: http://localhost:5000")
    print("📍 Press Ctrl+C to stop the server")
    print()
    print("="*60)
    print()
    
    # Start the API server
    api_path = base_dir / "api.py"
    try:
        subprocess.run([sys.executable, str(api_path)])
    except KeyboardInterrupt:
        print()
        print("="*60)
        print("Server stopped by user")
        print("="*60)

if __name__ == "__main__":
    main()
