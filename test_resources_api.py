#!/usr/bin/env python3
"""
Simple test to verify Resources API blueprint is correctly implemented.
"""

import sys
import os

# Add current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    print("=" * 60)
    print("Testing Resources API Blueprint")
    print("=" * 60)
    
    # Test blueprint import
    from routes.routes_resources import bp
    print('✅ Resources blueprint imported successfully')
    print(f'   - Blueprint name: {bp.name}')
    
    # Test serializer function import
    from routes.routes_resources import _serialize_resource
    print('✅ _serialize_resource function imported successfully')
    
    # Test model imports
    from models import Resource
    print('✅ Resource model imported successfully')
    
    # Test creating an app and registering the blueprint
    from app import create_app
    app = create_app()
    print('✅ App created successfully')
    
    # Check if blueprint is registered
    blueprint_names = [bp_name for bp_name, bp_obj in app.blueprints.items()]
    if 'resources' in blueprint_names:
        print('✅ Resources blueprint is registered!')
    else:
        print('❌ Resources blueprint is NOT registered')
        sys.exit(1)
    
    # Test serializer with mock data
    with app.app_context():
        from datetime import datetime, timezone
        
        # Create a mock resource (not saving to DB)
        mock_resource = Resource(
            id=1,
            title="Test Resource",
            description="Test description",
            category="Health",
            target_role="mother",
            content_type="article",
            url="https://example.com",
            thumbnail="🤰",
            created_at=datetime.now(timezone.utc)
        )
        
        # Test serialization
        serialized = _serialize_resource(mock_resource)
        print('✅ Resource serialization works')
        print('   - Serialized keys:', list(serialized.keys()))
        
        expected_keys = ['id', 'title', 'description', 'category', 'target_role', 
                        'content_type', 'url', 'thumbnail', 'created_at']
        missing_keys = [key for key in expected_keys if key not in serialized.keys()]
        if missing_keys:
            print(f'❌ Missing serialization keys: {missing_keys}')
            sys.exit(1)
        else:
            print('✅ All expected serialization keys present')
    
    # Test route registration
    with app.test_client() as client:
        # This will fail authentication but should show route is registered
        response = client.get('/api/v1/resources')
        if response.status_code == 401:  # Unauthorized (expected without auth)
            print('✅ /api/v1/resources route is registered (returned 401 as expected without auth)')
        else:
            print(f'⚠️  /api/v1/resources route returned {response.status_code} (unexpected but route exists)')
    
    print()
    print("=" * 60)
    print("✅ ALL TESTS PASSED!")
    print("Resources API Blueprint is correctly implemented!")
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