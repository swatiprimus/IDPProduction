#!/usr/bin/env python3
"""
Test script to verify page-level cache persistence
Tests Add, Edit, Delete operations on a specific page
"""

import requests
import json
import time

BASE_URL = "http://127.0.0.1:5015"

def test_page_cache_operations():
    """Test Add, Edit, Delete operations on Page 3"""
    
    print("\n" + "="*80)
    print("PAGE-LEVEL CACHE PERSISTENCE TEST")
    print("="*80)
    
    # You'll need to replace these with actual values from your system
    doc_id = input("\n📄 Enter Document ID (e.g., doc_123): ").strip()
    account_index = input("🏦 Enter Account Index (e.g., 0): ").strip()
    page_num = 3  # Testing Page 3
    
    if not doc_id or not account_index:
        print("❌ Document ID and Account Index are required")
        return
    
    try:
        account_index = int(account_index)
    except ValueError:
        print("❌ Account Index must be a number")
        return
    
    print(f"\n🎯 Testing Page {page_num} for Document: {doc_id}, Account: {account_index}")
    print("-" * 80)
    
    # Test 1: Add a new field
    print(f"\n✏️  TEST 1: ADD NEW FIELD TO PAGE {page_num}")
    print("-" * 80)
    
    add_payload = {
        "page_data": {
            "test_field_new": "Test Value Added",
            "another_field": "Another Test Value"
        },
        "action_type": "add",
        "account_index": account_index
    }
    
    print(f"📤 Sending ADD request to: /api/document/{doc_id}/account/{account_index}/page/{page_num}/update")
    print(f"📦 Payload: {json.dumps(add_payload, indent=2)}")
    
    response = requests.post(
        f"{BASE_URL}/api/document/{doc_id}/account/{account_index}/page/{page_num}/update",
        json=add_payload
    )
    
    print(f"\n📥 Response Status: {response.status_code}")
    response_data = response.json()
    print(f"📥 Response: {json.dumps(response_data, indent=2)}")
    
    if response.status_code == 200 and response_data.get("success"):
        print(f"✅ ADD SUCCESSFUL - Verified: {response_data.get('verified', False)}")
        print(f"✅ Cache Key: {response_data.get('cache_key', 'N/A')}")
    else:
        print(f"❌ ADD FAILED - {response_data.get('message', 'Unknown error')}")
        return
    
    # Wait a moment
    time.sleep(1)
    
    # Test 2: Retrieve the data to verify it was saved
    print(f"\n🔍 TEST 2: RETRIEVE PAGE {page_num} DATA (Verify Save)")
    print("-" * 80)
    
    print(f"📤 Sending GET request to: /api/document/{doc_id}/account/{account_index}/page/{page_num}/data")
    
    response = requests.get(
        f"{BASE_URL}/api/document/{doc_id}/account/{account_index}/page/{page_num}/data"
    )
    
    print(f"\n📥 Response Status: {response.status_code}")
    response_data = response.json()
    print(f"📥 Response: {json.dumps(response_data, indent=2)}")
    
    if response.status_code == 200 and response_data.get("success"):
        cached_data = response_data.get("data", {})
        print(f"✅ RETRIEVAL SUCCESSFUL")
        print(f"✅ Cache Source: {response_data.get('cache_source', 'N/A')}")
        print(f"✅ Fields in cache: {len(cached_data)}")
        
        # Check if our added fields are there
        if "test_field_new" in cached_data:
            print(f"✅ VERIFIED: 'test_field_new' found in cache with value: {cached_data['test_field_new']}")
        else:
            print(f"❌ PROBLEM: 'test_field_new' NOT found in cache!")
            print(f"   Available fields: {list(cached_data.keys())}")
    else:
        print(f"❌ RETRIEVAL FAILED - {response_data.get('message', 'Unknown error')}")
        return
    
    # Wait a moment
    time.sleep(1)
    
    # Test 3: Edit an existing field
    print(f"\n✏️  TEST 3: EDIT FIELD ON PAGE {page_num}")
    print("-" * 80)
    
    edit_payload = {
        "page_data": {
            "test_field_new": "Test Value EDITED"
        },
        "action_type": "edit",
        "account_index": account_index
    }
    
    print(f"📤 Sending EDIT request to: /api/document/{doc_id}/account/{account_index}/page/{page_num}/update")
    print(f"📦 Payload: {json.dumps(edit_payload, indent=2)}")
    
    response = requests.post(
        f"{BASE_URL}/api/document/{doc_id}/account/{account_index}/page/{page_num}/update",
        json=edit_payload
    )
    
    print(f"\n📥 Response Status: {response.status_code}")
    response_data = response.json()
    print(f"📥 Response: {json.dumps(response_data, indent=2)}")
    
    if response.status_code == 200 and response_data.get("success"):
        print(f"✅ EDIT SUCCESSFUL - Verified: {response_data.get('verified', False)}")
    else:
        print(f"❌ EDIT FAILED - {response_data.get('message', 'Unknown error')}")
        return
    
    # Wait a moment
    time.sleep(1)
    
    # Test 4: Retrieve again to verify edit
    print(f"\n🔍 TEST 4: RETRIEVE PAGE {page_num} DATA (Verify Edit)")
    print("-" * 80)
    
    response = requests.get(
        f"{BASE_URL}/api/document/{doc_id}/account/{account_index}/page/{page_num}/data"
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
    
    # Wait a moment
    time.sleep(1)
    
    # Test 5: Delete a field
    print(f"\n🗑️  TEST 5: DELETE FIELD FROM PAGE {page_num}")
    print("-" * 80)
    
    delete_payload = {
        "page_data": {},
        "action_type": "delete",
        "deleted_fields": ["test_field_new"],
        "account_index": account_index
    }
    
    print(f"📤 Sending DELETE request to: /api/document/{doc_id}/account/{account_index}/page/{page_num}/update")
    print(f"📦 Payload: {json.dumps(delete_payload, indent=2)}")
    
    response = requests.post(
        f"{BASE_URL}/api/document/{doc_id}/account/{account_index}/page/{page_num}/update",
        json=delete_payload
    )
    
    print(f"\n📥 Response Status: {response.status_code}")
    response_data = response.json()
    print(f"📥 Response: {json.dumps(response_data, indent=2)}")
    
    if response.status_code == 200 and response_data.get("success"):
        print(f"✅ DELETE SUCCESSFUL - Verified: {response_data.get('verified', False)}")
    else:
        print(f"❌ DELETE FAILED - {response_data.get('message', 'Unknown error')}")
        return
    
    # Wait a moment
    time.sleep(1)
    
    # Test 6: Retrieve again to verify delete
    print(f"\n🔍 TEST 6: RETRIEVE PAGE {page_num} DATA (Verify Delete)")
    print("-" * 80)
    
    response = requests.get(
        f"{BASE_URL}/api/document/{doc_id}/account/{account_index}/page/{page_num}/data"
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

if __name__ == "__main__":
    test_page_cache_operations()
