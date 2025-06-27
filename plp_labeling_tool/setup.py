#!/usr/bin/env python3
"""
Setup script for the PLP Labeling Tool.
This script helps install dependencies and set up the environment.
"""

import subprocess
import sys
import os
from pathlib import Path


def run_command(command, description):
    """Run a command and handle errors."""
    print(f"\n{description}...")
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print(f"✓ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ {description} failed:")
        print(f"  Command: {command}")
        print(f"  Error: {e.stderr}")
        return False


def check_python_version():
    """Check if Python version is compatible."""
    version = sys.version_info
    if version < (3, 8):
        print(f"✗ Python 3.8+ required, but you have {version.major}.{version.minor}")
        return False
    print(f"✓ Python {version.major}.{version.minor}.{version.micro} is compatible")
    return True


def main():
    """Main setup function."""
    print("PLP Labeling Tool Setup")
    print("=" * 30)
    
    # Check Python version
    if not check_python_version():
        sys.exit(1)
    
    # Install Python dependencies
    if not run_command("pip install -r requirements.txt", "Installing Python dependencies"):
        print("Consider using a virtual environment:")
        print("  python -m venv venv")
        print("  source venv/bin/activate  # On Windows: venv\\Scripts\\activate")
        print("  pip install -r requirements.txt")
        sys.exit(1)
    
    # Install Playwright browsers
    if not run_command("playwright install chromium", "Installing Playwright browsers"):
        print("You may need to install Playwright manually:")
        print("  pip install playwright")
        print("  playwright install chromium")
        sys.exit(1)
    
    # Optional: Install NLP dependencies
    parent_req = Path("../requirements_nlp.txt")
    if parent_req.exists():
        print("\nOptional: Install NLP dependencies for content filtering?")
        response = input("This will install additional ML libraries (y/N): ").lower()
        if response in ['y', 'yes']:
            if run_command(f"pip install -r {parent_req}", "Installing NLP dependencies"):
                print("✓ NLP dependencies installed - content filtering will be available")
            else:
                print("! NLP dependencies failed to install - content filtering will be disabled")
    
    # Create data directory
    data_dir = Path("plp_data")
    data_dir.mkdir(exist_ok=True)
    print(f"✓ Created data directory: {data_dir.absolute()}")
    
    # Check if database exists
    db_paths = ["../crawler_data.db", "crawler_data.db"]
    db_found = False
    for db_path in db_paths:
        if Path(db_path).exists():
            print(f"✓ Found database: {Path(db_path).absolute()}")
            db_found = True
            break
    
    if not db_found:
        print("! No database found. You can:")
        print("  - Use --urls-file to load URLs from a text file")
        print("  - Use --json-file to load URLs from a JSON file")
        print("  - Create a database using the main crawler project")
    
    print("\n" + "=" * 50)
    print("Setup completed successfully!")
    print("\nNext steps:")
    print("1. Test the installation:")
    print("   python main.py --help")
    print("\n2. Start labeling with sample data:")
    print("   python main.py --sample-size 10")
    print("\n3. Or load URLs from a file:")
    print("   python main.py --urls-file my_urls.txt")
    print("\nFor more information, see README.md")


if __name__ == "__main__":
    main() 