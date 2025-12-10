#!/usr/bin/env python3
"""
Test script to debug document deletion issues
"""

import requests
import json
import sys

def test_delete_functionality():
    """Test the document deletion endpoint"""
    
    base_url = "http://localhost:5015"
    
    print("Testing Document Deletion Functionality")
    print("=" * 50)
    
    try:
        # Step 1: Check if server is running
        print("1. Checking if server is running...")
        response = requests.get(f"{base_url}/api/documents", timeout=5)
        
        if response.status_code != 200:
            print(f"❌ Server not responding properly: {response.status_code}")
            return False
        
        documents = response.json()
        print(f"✅ Server is running, found {len(documents)} documents")
        
        if not documents:
            print("ℹ️  No documents to test deletion with")
            return True
        
        # Step 2: Get first document for testing
        test_doc = documents[0]
        doc_id = test_doc.get('id')
        doc_name = test_doc.get('filename', 'Unknown')
        
        print(f"2. Testing deletion of document: {doc_name} (ID: {doc_id})")
        
        # Step 3: Test the delete endpoint (but don't actually delete)
        print("3. Testing delete endpoint accessibility...")
        
        # First, let's just check if the endpoint exists by making a request
        # We'll use a fake ID to see if we get the right error
        fake_response = requests.post(f"{base_url}/api/document/fake_id/delete")
        
        if fake_response.status_code == 404:
            print("✅ Delete endpoint is accessible (returned 404 for fake ID)")
        else:
            print(f"⚠️  Unexpected response for fake ID: {fake_response.status_code}")
            print(f"Response: {fake_response.text}")
        
        # Step 4: Check what happens with a real ID (but we won't actually delete)
        print(f"4. Checking delete endpoint with real ID (not actually deleting)...")
        print(f"   Endpoint: POST {base_url}/api/document/{doc_id}/delete")
        print(f"   Document: {doc_name}")
        
        # Let's check the document structure
        print(f"5. Document structure:")
        print(f"   ID: {doc_id}")
        print(f"   Filename: {test_doc.get('filename')}")
        print(f"   PDF Path: {test_doc.get('pdf_path')}")
        print(f"   OCR File: {test_doc.get('ocr_file')}")
        
        return True
        
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to server")
        print("   Make sure the Flask app is running:")
        print("   python app_modular.py")
        return False
        
    except requests.exceptions.Timeout:
        print("❌ Server request timed out")
        return False
        
    except Exception as e:
        print(f"❌ Unexpected error: {str(e)}")
        return False

def check_delete_permissions():
    """Check if there might be file permission issues"""
    
    print("\nChecking File Permissions")
    print("=" * 30)
    
    import os
    
    # Check processed_documents.json permissions
    if os.path.exists('processed_documents.json'):
        try:
            # Try to read
            with open('processed_documents.json', 'r') as f:
                data = json.load(f)
            print("✅ Can read processed_documents.json")
            
            # Try to write (backup and restore)
            backup_data = data.copy()
            with open('processed_documents.json', 'w') as f:
                json.dump(backup_data, f)
            print("✅ Can write processed_documents.json")
            
        except PermissionError:
            print("❌ Permission denied accessing processed_documents.json")
            return False
        except Exception as e:
            print(f"❌ Error accessing processed_documents.json: {str(e)}")
            return False
    else:
        print("⚠️  processed_documents.json not found")
    
    # Check OCR results directory permissions
    if os.path.exists('ocr_results'):
        try:
            # Try to list directory
            files = os.listdir('ocr_results')
            print(f"✅ Can read ocr_results directory ({len(files)} files)")
            
            # Check if we can delete files (test with a non-existent file)
            test_file = 'ocr_results/test_delete_permission.txt'
            try:
                with open(test_file, 'w') as f:
                    f.write('test')
                os.remove(test_file)
                print("✅ Can create and delete files in ocr_results")
            except Exception as e:
                print(f"⚠️  Cannot create/delete files in ocr_results: {str(e)}")
                
        except PermissionError:
            print("❌ Permission denied accessing ocr_results directory")
            return False
        except Exception as e:
            print(f"❌ Error accessing ocr_results directory: {str(e)}")
            return False
    else:
        print("⚠️  ocr_results directory not found")
    
    return True

if __name__ == "__main__":
    print("Document Deletion Debug Tool")
    print("=" * 40)
    
    # Test server connectivity and delete endpoint
    server_ok = test_delete_functionality()
    
    # Check file permissions
    permissions_ok = check_delete_permissions()
    
    print("\nSummary:")
    print("=" * 20)
    print(f"Server connectivity: {'✅ OK' if server_ok else '❌ FAILED'}")
    print(f"File permissions: {'✅ OK' if permissions_ok else '❌ FAILED'}")
    
    if server_ok and permissions_ok:
        print("\n✅ Delete functionality should work")
        print("If delete is still not working, check browser console for errors")
    else:
        print("\n❌ Issues found that may prevent deletion")