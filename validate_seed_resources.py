#!/usr/bin/env python3
"""
Test script to verify seed_resources.py follows the correct pattern and syntax
"""

import sys
import os
import ast

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def validate_seed_resources():
    """Validate the seed_resources.py file"""
    print("=" * 60)
    print("Validating seed_resources.py")
    print("=" * 60)
    
    script_path = os.path.join(os.path.dirname(__file__), 'seed_resources.py')
    
    if not os.path.exists(script_path):
        print("❌ seed_resources.py not found")
        return False
    
    try:
        # Check syntax
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        ast.parse(content, filename=script_path)
        print("✅ Syntax validation passed")
        
        # Check for required imports
        required_imports = ['create_app', 'db', 'Resource', 'datetime', 'timezone']
        for import_name in required_imports:
            if import_name in content:
                print(f"✅ Required import found: {import_name}")
            else:
                print(f"❌ Missing required import: {import_name}")
                return False
        
        # Check for resource data structure
        if 'resources_data = [' in content:
            print("✅ resources_data structure found")
        else:
            print("❌ resources_data structure not found")
            return False
        
        # Count expected resources (15 total: 5 each for mother, chw, nurse)
        mother_count = content.count('"target_role": "mother"')
        chw_count = content.count('"target_role": "chw"')
        nurse_count = content.count('"target_role": "nurse"')
        
        print(f"✅ Mother resources: {mother_count}")
        print(f"✅ CHW resources: {chw_count}")
        print(f"✅ Nurse resources: {nurse_count}")
        
        if mother_count == 5 and chw_count == 5 and nurse_count == 5:
            print("✅ Correct resource distribution (5 each)")
        else:
            print("❌ Incorrect resource distribution")
            return False
        
        # Check for required fields in resources
        required_fields = ['title', 'description', 'category', 'target_role', 'content_type', 'url', 'thumbnail']
        for field in required_fields:
            if f'"{field}":' in content:
                print(f"✅ Required field found in resources: {field}")
            else:
                print(f"❌ Missing required field: {field}")
                return False
        
        # Check for proper main execution
        if 'if __name__ == "__main__":' in content:
            print("✅ Main execution guard found")
        else:
            print("❌ Main execution guard not found")
            return False
        
        print("\n" + "=" * 60)
        print("✅ ALL VALIDATIONS PASSED!")
        print("seed_resources.py is ready to use")
        print("=" * 60)
        return True
        
    except SyntaxError as e:
        print(f"❌ Syntax error: {e}")
        return False
    except Exception as e:
        print(f"❌ Validation error: {e}")
        return False

if __name__ == "__main__":
    success = validate_seed_resources()
    if not success:
        sys.exit(1)