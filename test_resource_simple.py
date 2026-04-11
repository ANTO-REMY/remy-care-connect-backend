#!/usr/bin/env python3
"""
Simple test to verify Resource model can be imported and has required fields.
"""

import sys
import os

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    print("=" * 60)
    print("Testing Resource Model Import and Fields")
    print("=" * 60)
    
    from models import Resource
    print('✅ Resource model imported successfully')
    
    # Get table name
    print(f'✅ Resource table name: {Resource.__tablename__}')
    
    # Get column information
    columns = [column.key for column in Resource.__table__.columns]
    print(f'✅ Resource columns ({len(columns)}): {columns}')
    
    # Check for the required fields
    required_fields = ['id', 'title', 'description', 'category', 'target_role', 'content_type', 'url', 'thumbnail', 'created_at']
    missing_fields = [field for field in required_fields if field not in columns]
    
    if missing_fields:
        print(f'❌ FAILED: Missing fields: {missing_fields}')
        sys.exit(1)
    else:
        print('✅ All required fields present:')
        for field in required_fields:
            print(f'   - {field}')
    
    # Check table constraints
    print('✅ Table constraints:')
    constraints = list(Resource.__table__.constraints)
    if constraints:
        for constraint in constraints:
            print(f'   - {constraint.name}: {type(constraint).__name__}')
    else:
        print('   - (none)')
    
    # Test creating a Resource instance (without database)
    resource = Resource(
        title="Test Resource",
        target_role="mother",
        description="Test description"
    )
    print('✅ Resource instance created successfully')
    print(f'   - title: {resource.title}')
    print(f'   - target_role: {resource.target_role}')
    print(f'   - description: {resource.description}')
    
    print()
    print("=" * 60)
    print("✅ ALL TESTS PASSED!")
    print("=" * 60)
    
except ImportError as e:
    print(f'❌ Import error: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
except Exception as e:
    print(f'❌ Error: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
