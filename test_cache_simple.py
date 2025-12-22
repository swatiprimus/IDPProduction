#!/usr/bin/env python3
"""
Simple test to verify page-level cache persistence
Uses actual document from the system
"""

import requests
import json
import time

BASE_URL = "http://127.0.0.1:5015"

# Use actual document from the system
DOC_ID = "b1156ab1d4f3"
ACCOUNT_INDEX = 0
PAGE_NUM = 3  # Testing Page 3

print("\n" + "="*80)
print("PAGE-LEVEL CACHE PERSISTENCE TEST")
print("="*80)
print(f"\n📄 Document ID: {DOC_ID}")
print(f"🏦 Account Index: {ACCOUNT_INDEX}")
print(f"📄 Page Number: {PAGE_NUM}")
print("-" * 80)

# Test 1: Add a new field
print(f"\n✏️  TEST 1: ADD NEW FIELD TO PAGE {PAGE_NUM}")
print("-" * 80)

add_payload = {
    "page_data": {
        "test_field_new": "Test Value Added",
        "another_field": "Another Test Value"
    },
    "action_type": "add",
    "account_index": ACCOUNT_INDEX
}

print(f"📤 Sending ADD request...")
print(f"📦 Payload: {json.dumps(add_payload, indent=2)}")

response = requests.post(
    f"{BASE_URL}/api/document/{DOC_ID}/account/{ACCOUNT_INDEX}/page/{PAGE_NUM}/update",
    json=add_payload
)

print(f"\n📥 Response Status: {response.status_code}")
response_data = response.json()
print(f"📥 Response: {json.dumps(response_data, indent=2)}")

if response.status_code == 200 and response_data.get("success"):
    print(f"✅ ADD SUCCESSFUL")
    print(f"   - Verified: {response_data.get('verified', False)}")
    print(f"   - Cache Key: {response_data.get('cache_key', 'N/A')}")
else:
    print(f"❌ ADD FAILED - {response_data.get('message', 'Unknown error')}")

time.sleep(1)

# Test 2: Retrieve the data to verify it was saved
print(f"\n🔍 TEST 2: RETRIEVE PAGE {PAGE_NUM} DATA (Verify Save)")
print("-" * 80)

print(f"📤 Sending GET request...")

response = requests.get(
    f"{BASE_URL}/api/document/{DOC_ID}/account/{ACCOUNT_INDEX}/page/{PAGE_NUM}/data"
)

print(f"\n📥 Response Status: {response.status_code}")
response_data = response.json()

if response.status_code == 200 and response_data.get("success"):
    cached_data = response_data.get("data", {})
    print(f"✅ RETRIEVAL SUCCESSFUL")
    print(f"   - Cache Source: {response_data.get('cache_source', 'N/A')}")
    print(f"   - Fields in cache: {len(cached_data)}")
    
    # Check if our added fields are there
    if "test_field_new" in cached_data:
        field_value = cached_data["test_field_new"]
        if isinstance(field_value, dict):
            actual_value = field_value.get("value", field_value)
        else:
            actual_value = field_value
        print(f"✅ VERIFIED: 'test_field_new' found in cache")
        print(f"   - Value: {actual_value}")
    else:
        print(f"❌ PROBLEM: 'test_field_new' NOT found in cache!")
        print(f"   - Available fields: {list(cached_data.keys())}")
else:
    print(f"❌ RETRIEVAL FAILED")
    print(f"   - Response: {json.dumps(response_data, indent=2)}")

time.sleep(1)

# Test 3: Edit the field
print(f"\n✏️  TEST 3: EDIT FIELD ON PAGE {PAGE_NUM}")
print("-" * 80)

edit_payload = {
    "page_data": {
        "test_field_new": "Test Value EDITED"
    },
    "action_type": "edit",
    "account_index": ACCOUNT_INDEX
}

print(f"📤 Sending EDIT request...")
print(f"📦 Payload: {json.dumps(edit_payload, indent=2)}")

response = requests.post(
    f"{BASE_URL}/api/document/{DOC_ID}/account/{ACCOUNT_INDEX}/page/{PAGE_NUM}/update",
    json=edit_payload
)

print(f"\n📥 Response Status: {response.status_code}")
response_data = response.json()

if response.status_code == 200 and response_data.get("success"):
    print(f"✅ EDIT SUCCESSFUL")
    print(f"   - Verified: {response_data.get('verified', False)}")
else:
    print(f"❌ EDIT FAILED - {response_data.get('message', 'Unknown error')}")

time.sleep(1)

# Test 4: Retrieve again to verify edit
print(f"\n🔍 TEST 4: RETRIEVE PAGE {PAGE_NUM} DATA (Verify Edit)")
print("-" * 80)

response = requests.get(
    f"{BASE_URL}/api/document/{DOC_ID}/account/{ACCOUNT_INDEX}/page/{PAGE_NUM}/data"
)

print(f"\n📥 Response Status: {response.status_code}")
response_data = response.json()

if response.status_code == 200 and response_data.get("success"):
    cached_data = response_data.get("data", {})
    print(f"✅ RETRIEVAL SUCCESSFUL")
    
    if "test_field_new" in cached_data:
        field_value = cached_data["test_field_new"]
        if isinstance(field_value, dict):
            actual_value = field_value.get("value", field_value)
        else:
            actual_value = field_value
        
        print(f"✅ VERIFIED: 'test_field_new' = {actual_value}")
        
        if actual_value == "Test Value EDITED":
            print(f"✅ EDIT VERIFIED: Value was successfully updated!")
        else:
            print(f"❌ PROBLEM: Value was not updated. Expected 'Test Value EDITED', got '{actual_value}'")
    else:
        print(f"❌ PROBLEM: 'test_field_new' NOT found in cache!")
else:
    print(f"❌ RETRIEVAL FAILED")

time.sleep(1)

# Test 5: Delete the field
print(f"\n🗑️  TEST 5: DELETE FIELD FROM PAGE {PAGE_NUM}")
print("-" * 80)

delete_payload = {
    "page_data": {},
    "action_type": "delete",
    "deleted_fields": ["test_field_new"],
    "account_index": ACCOUNT_INDEX
}

print(f"📤 Sending DELETE request...")
print(f"📦 Payload: {json.dumps(delete_payload, indent=2)}")

response = requests.post(
    f"{BASE_URL}/api/document/{DOC_ID}/account/{ACCOUNT_INDEX}/page/{PAGE_NUM}/update",
    json=delete_payload
)

print(f"\n📥 Response Status: {response.status_code}")
response_data = response.json()

if response.status_code == 200 and response_data.get("success"):
    print(f"✅ DELETE SUCCESSFUL")
    print(f"   - Verified: {response_data.get('verified', False)}")
else:
    print(f"❌ DELETE FAILED - {response_data.get('message', 'Unknown error')}")

time.sleep(1)

# Test 6: Retrieve again to verify delete
print(f"\n🔍 TEST 6: RETRIEVE PAGE {PAGE_NUM} DATA (Verify Delete)")
print("-" * 80)

response = requests.get(
    f"{BASE_URL}/api/document/{DOC_ID}/account/{ACCOUNT_INDEX}/page/{PAGE_NUM}/data"
)

print(f"\n📥 Response Status: {response.status_code}")
response_data = response.json()

if response.status_code == 200 and response_data.get("success"):
    cached_data = response_data.get("data", {})
    print(f"✅ RETRIEVAL SUCCESSFUL")
    
    if "test_field_new" not in cached_data:
        print(f"✅ DELETE VERIFIED: 'test_field_new' was successfully removed!")
    else:
        print(f"❌ PROBLEM: 'test_field_new' still exists in cache!")
else:
    print(f"❌ RETRIEVAL FAILED")

# Summary
print("\n" + "="*80)
print("TEST SUMMARY")
print("="*80)
print("""
✅ If all tests passed:
   - Page-level cache is working correctly
   - Add, Edit, Delete operations persist data
   - Data survives page refresh
   
❌ If any test failed:
   - Check the error messages above
   - Review server logs for details
   - Check cache key format in logs
   - Verify S3 permissions
""")
print("="*80 + "\n")
