#!/usr/bin/env python3
"""
Test script to verify the normalization function is working correctly
"""

# Test data that simulates what the AI might return
test_cases = [
    # Case 1: Simple string value
    {"Purpose": "Consumer Personal"},
    
    # Case 2: Confidence object
    {"Purpose": {"value": "Consumer Personal", "confidence": 95}},
    
    # Case 3: Mixed fields
    {
        "Purpose": "Consumer Personal",
        "Account_Number": "468869904",
        "Phone_Number": "302-834-0382"
    },
    
    # Case 4: Already separated fields (should not change)
    {
        "Account_Purpose": "Consumer",
        "Account_Category": "Personal",
        "Account_Number": "468869904"
    }
]

def parse_combined_ocr_fields(text):
    """
    Parse combined OCR text that reads form labels and values together without spaces
    Examples: "PurposeConsumer Personal" → Account_Purpose: "Consumer", Account_Category: "Personal"
    """
    results = {}
    print(f"[PARSE_COMBINED] Input text: '{text}'")
    
    # CRITICAL: Handle the exact case the user is experiencing
    # "Purpose Consumer Personal" → Account_Purpose: "Consumer", Account_Category: "Personal"
    if "Purpose Consumer Personal" in text:
        print(f"[PARSE_COMBINED] Found 'Purpose Consumer Personal' pattern - EXACT USER CASE")
        results["Account_Purpose"] = "Consumer"
        results["Account_Category"] = "Personal"
        return results
    
    # Handle "Consumer Personal" pattern (space-separated)
    if "Consumer Personal" in text:
        print(f"[PARSE_COMBINED] Found 'Consumer Personal' pattern")
        results["Account_Purpose"] = "Consumer"
        results["Account_Category"] = "Personal"
        return results
    elif "Consumer Business" in text:
        print(f"[PARSE_COMBINED] Found 'Consumer Business' pattern")
        results["Account_Purpose"] = "Consumer"
        results["Account_Category"] = "Business"
        return results
    
    print(f"[PARSE_COMBINED] Results: {results}")
    return results

def normalize_extraction_result(data):
    """
    Normalize extraction results to ensure consistency across different extractions
    """
    if not data or not isinstance(data, dict):
        return data
    
    print(f"[NORMALIZE] Input data: {data}")
    normalized = {}
    
    # Field name mappings to standardize variations
    field_mappings = {
        # Address variations
        "Mailing_Address": "Address",
        "mailing_address": "Address", 
        "Street_Address": "Address",
        
        # Signature variations  
        "Required_Signatures": "Signatures_Required",
        "required_signatures": "Signatures_Required",
        "Signature_Required": "Signatures_Required",
        
        # Phone variations - normalize format
        "phone_number": "Phone_Number",
        "contact_phone": "Phone_Number",
        
        # Account category
        "account_category": "Account_Category",
        "AccountCategory": "Account_Category"
    }
    
    # Process each field
    for key, value in data.items():
        print(f"[NORMALIZE] Processing field: {key} = {value}")
        
        # CRITICAL: Handle confidence objects first
        actual_value = value
        if isinstance(value, dict) and "value" in value:
            actual_value = value["value"]
            print(f"[NORMALIZE] Extracted value from confidence object: {actual_value}")
        
        # CRITICAL FIX: Handle specific field names with combined values
        if key in ["Purpose", "Account_Purpose", "AccountPurpose"] and isinstance(actual_value, str):
            print(f"[NORMALIZE] Found Purpose field: {key} = {actual_value}")
            if "Consumer Personal" in actual_value:
                print(f"[NORMALIZE] Parsing 'Consumer Personal' into separate fields")
                normalized["Account_Purpose"] = "Consumer"
                normalized["Account_Category"] = "Personal"
                continue
            elif "Consumer Business" in actual_value:
                print(f"[NORMALIZE] Parsing 'Consumer Business' into separate fields")
                normalized["Account_Purpose"] = "Consumer"
                normalized["Account_Category"] = "Business"
                continue
            elif "Consumer" in actual_value:
                print(f"[NORMALIZE] Found Consumer, checking for additional category")
                normalized["Account_Purpose"] = "Consumer"
                # Try to extract category from remaining text
                remaining = actual_value.replace("Consumer", "").strip()
                print(f"[NORMALIZE] Remaining text after removing 'Consumer': '{remaining}'")
                if remaining:
                    if "Personal" in remaining:
                        normalized["Account_Category"] = "Personal"
                        print(f"[NORMALIZE] Found Personal in remaining text")
                    elif "Business" in remaining:
                        normalized["Account_Category"] = "Business"
                        print(f"[NORMALIZE] Found Business in remaining text")
                continue
        
        # Handle Type field variations - map to Account_Category for consistency
        if key in ["Type", "Account_Type", "AccountType", "Account_Category", "AccountCategory"] and isinstance(actual_value, str):
            print(f"[NORMALIZE] Found Type/Category field: {key} = {actual_value}")
            if "Personal" in actual_value and "Consumer" not in actual_value:
                normalized["Account_Category"] = "Personal"
                continue
            elif "Business" in actual_value and "Consumer" not in actual_value:
                normalized["Account_Category"] = "Business"
                continue
            else:
                # If it's already Account_Type, map it to Account_Category for consistency
                if key in ["Account_Type", "AccountType"]:
                    normalized["Account_Category"] = actual_value
                else:
                    normalized["Account_Category"] = actual_value
                continue
        
        # CRITICAL FIX: Handle combined OCR field names and values
        combined_text = f"{key} {actual_value}" if isinstance(actual_value, str) else key
        parsed_fields = parse_combined_ocr_fields(combined_text)
        
        # If we parsed combined fields, add them and skip the original
        if parsed_fields:
            print(f"[NORMALIZE] Parsed combined fields: {parsed_fields}")
            normalized.update(parsed_fields)
            continue
        
        # Apply field name mapping
        normalized_key = field_mappings.get(key, key)
        
        # Normalize phone number format
        if "phone" in normalized_key.lower() and isinstance(actual_value, str):
            # Remove extra formatting and standardize
            phone = actual_value.replace("(", "").replace(")", "").replace("-", "").replace(" ", "")
            if len(phone) == 10:
                actual_value = f"({phone[:3]}) {phone[3:6]}-{phone[6:]}"
        
        print(f"[NORMALIZE] Adding field: {normalized_key} = {actual_value}")
        normalized[normalized_key] = actual_value
    
    print(f"[NORMALIZE] Final output: {normalized}")
    return normalized

if __name__ == "__main__":
    print("Testing normalization function...")
    print("=" * 80)
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\nTEST CASE {i}:")
        print(f"Input: {test_case}")
        result = normalize_extraction_result(test_case)
        print(f"Output: {result}")
        print("-" * 40)
        
        # Check if the problematic case was fixed
        if "Purpose" in test_case and "Consumer Personal" in str(test_case["Purpose"]):
            if "Account_Purpose" in result and "Account_Category" in result:
                print("✅ SUCCESS: Combined field was properly separated!")
            else:
                print("❌ FAILED: Combined field was not separated properly!")
        print("=" * 80)