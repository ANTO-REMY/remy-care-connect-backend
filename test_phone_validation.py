#!/usr/bin/env python3
"""
Test phone number normalization and validation
"""

import re

def normalize_phone_number(phone):
    """Normalize phone number to +254xxx format"""
    # Remove all spaces and special characters except +
    cleaned = re.sub(r'[^0-9+]', '', phone)
    
    # Handle different formats
    if cleaned.startswith('07') and len(cleaned) == 10:
        # Convert 07xxxxxxxx to +254xxxxxxxx
        return '+254' + cleaned[1:]
    elif cleaned.startswith('+2547') and len(cleaned) == 13:
        # Convert +2547xxxxxxxx to +254xxxxxxxx
        return '+254' + cleaned[5:]
    elif cleaned.startswith('+254') and len(cleaned) == 13:
        # Already in correct format - don't modify
        return cleaned
    elif cleaned.startswith('254') and len(cleaned) == 12:
        # Convert 254xxxxxxxx to +254xxxxxxxx
        return '+' + cleaned
    
    # If none of the above, return as is (will fail validation)
    return phone

def validate_phone_number(phone):
    """Validate Kenyan phone number format"""
    # Check if it's in correct format and starts with valid Kenyan prefixes
    # Kenyan numbers: +254 + [7,1] + 8 more digits = 13 total characters
    pattern = r'^\+254[71][0-9]{8}$'
    return bool(re.match(pattern, phone))

# Test cases
test_phones = [
    '0700000001',
    '+254700000001', 
    '0712345678',
    '+254712345678',
    '+2547123456789',  # Too many digits
    '+254112345678',   # Starts with 11
    '0800000001',      # Invalid prefix 08
    '+254800000001',   # Invalid prefix 8
]

print("📱 Testing phone number normalization and validation:")
print("=" * 60)

for phone in test_phones:
    normalized = normalize_phone_number(phone)
    is_valid = validate_phone_number(normalized)
    status = "✅ VALID" if is_valid else "❌ INVALID"
    
    print(f"Input: {phone:15} → Normalized: {normalized:15} → {status}")

print("\n🧪 Specific test cases from user:")
print("-" * 40)

user_inputs = ['0700000001', '+254700000001']
for phone in user_inputs:
    normalized = normalize_phone_number(phone)
    is_valid = validate_phone_number(normalized)
    status = "✅ SHOULD WORK" if is_valid else "❌ WILL FAIL"
    
    print(f"{phone} → {normalized} → {status}")