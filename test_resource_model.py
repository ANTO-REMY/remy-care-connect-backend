#!/usr/bin/env python3
"""
Test script to validate the Resource model can be imported successfully.
"""

import sys
import os

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_resource_model():
    try:
        from models import Resource
        print('✅ Resource model imported successfully')
        print(f'✅ Resource table name: {Resource.__tablename__}')
        
        # Get column information
        columns = [column.key for column in Resource.__table__.columns]
        print(f'✅ Resource columns: {columns}')
        
        # Check for the required fields
        required_fields = ['id', 'title', 'description', 'category', 'target_role', 'content_type', 'url', 'thumbnail', 'created_at']
        missing_fields = [field for field in required_fields if field not in columns]
        
        if missing_fields:
            print(f'❌ Missing fields: {missing_fields}')
        else:
            print('✅ All required fields present')
            
        # Check table constraints
        print('✅ Table constraints:')
        for constraint in Resource.__table__.constraints:
            print(f'  - {constraint.name}: {constraint}')
            
        # Test creating a Resource instance
        resource = Resource(
            title="Test Resource",
            target_role="mother",
            description="Test description"
        )
        print('✅ Resource instance created successfully')
        print(f'✅ Resource title: {resource.title}')
        print(f'✅ Resource target_role: {resource.target_role}')
        
        return True
        
    except ImportError as e:
        print(f'❌ Import error: {e}')
        return False
    except Exception as e:
        print(f'❌ Other error: {e}')
        return False

if __name__ == '__main__':
    success = test_resource_model()
    exit(0 if success else 1)