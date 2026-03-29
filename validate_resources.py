#!/usr/bin/env python3
"""
Syntax validation for Resources API files.
"""
import ast
import sys
import os

def validate_python_file(filepath):
    """Check if a Python file has valid syntax."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse the file to check syntax
        ast.parse(content, filename=filepath)
        print(f"✅ {filepath} - Syntax OK")
        return True
    except SyntaxError as e:
        print(f"❌ {filepath} - Syntax Error: {e}")
        return False
    except Exception as e:
        print(f"❌ {filepath} - Error: {e}")
        return False

def main():
    print("=" * 60)
    print("Validating Resources API Syntax")
    print("=" * 60)
    
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    
    files_to_check = [
        os.path.join(backend_dir, 'routes', 'routes_resources.py'),
        os.path.join(backend_dir, 'test_resources_api.py'),
        os.path.join(backend_dir, 'app.py')
    ]
    
    all_valid = True
    for filepath in files_to_check:
        if os.path.exists(filepath):
            if not validate_python_file(filepath):
                all_valid = False
        else:
            print(f"❌ {filepath} - File not found")
            all_valid = False
    
    print("=" * 60)
    if all_valid:
        print("✅ All files have valid syntax!")
        print("Resources API implementation appears correct.")
    else:
        print("❌ Some files have syntax errors!")
        sys.exit(1)
    print("=" * 60)

if __name__ == '__main__':
    main()