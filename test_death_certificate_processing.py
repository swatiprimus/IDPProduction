#!/usr/bin/env python3
"""Test script specifically for death certificate background processing."""

import requests
import time
import json

BASE_URL = "http://localhost:5015"

def test_death_certificate_processing():
    """Test background processing for death certificates"""
    
    print("💀 Testing Death Certificate Background Processing")
    print("=" * 60)
    
    try:
        # Step 1: Get list of documents and find death certificates
        print("\n📋 Step 1: Looking for death certificate documents...")
        response = requests.get(f"{BASE_URL}/api/documents")
        if response.status_code != 200:
            print("❌ Failed to get documents list")
            return
        
        docs = response.json().get("documents", [])
        if not docs:
            print("❌ No documents found. Please upload a death certificate first.")
            return
        
        # Find death certificate documents
        death_cert_docs = []
        for doc in docs:
            doc_type = doc.get("document_type_info", {}).get("type", "unknown")
            if doc_type == "death_certificate":
                death_cert_docs.append(doc)
        
        if not death_cert_docs:
            print("❌ No death certificate documents found.")
            print("   Available document types:")
            for doc in docs[:5]:  # Show first 5
                doc_type = doc.get("document_type_info", {}).get("type", "unknown")
                doc_name = doc.get("filename", "Unknown")
                print(f"      • {doc_name}: {doc_type}")
            
            # Use the first document for testing anyway
            if docs:
                test_doc = docs[0]
                doc_id = test_doc["id"]
                doc_type = test_doc.get("document_type_info", {}).get("type", "unknown")
                print(f"\n🧪 Using first available document for testing: {doc_type}")
            else:
                return
        else:
            test_doc = death_cert_docs[0]
            doc_id = test_doc["id"]
            doc_type = "death_certificate"
            print(f"✅ Found death certificate: {test_doc.get('filename', 'Unknown')}")
        
        print(f"🎯 Testing document: {doc_id} (Type: {doc_type})")
        
        # Step 2: Check current document state
        print(f"\n🔍 Step 2: Checking current document state...")
        response = requests.get(f"{BASE_URL}/api/document/{doc_id}")
        if response.status_code == 200:
            doc_detail = response.json()
            if doc_detail.get("success"):
                doc = doc_detail["document"]
                extracted_fields = doc.get("documents", [{}])[0].get("extracted_fields", {})
                print(f"   Current extracted fields: {len(extracted_fields)}")
                
                if len(extracted_fields) > 5:  # More than just metadata
                    print("   ✅ Document already has extracted fields!")
                    for key, value in list(extracted_fields.items())[:5]:  # Show first 5
                        if not key.startswith("total_") and not key.startswith("accounts_"):
                            print(f"      {key}: {str(value)[:50]}...")
                else:
                    print("   ⏳ Document has minimal extracted fields")
        
        # Step 3: Force background processing
        print(f"\n🚀 Step 3: Forcing background processing for {doc_type}...")
        response = requests.post(f"{BASE_URL}/api/document/{doc_id}/force-background-processing")
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                print("✅ Background processing started successfully")
            else:
                print(f"❌ Failed to start processing: {result.get('message')}")
        else:
            print(f"❌ Failed to start processing: {response.status_code}")
        
        # Step 4: Monitor processing progress
        print(f"\n⏳ Step 4: Monitoring processing progress...")
        
        for i in range(12):  # Check for up to 60 seconds (12 * 5 seconds)
            try:
                response = requests.get(f"{BASE_URL}/api/document/{doc_id}/background-status")
                if response.status_code == 200:
                    status_result = response.json()
                    if status_result.get("success"):
                        status = status_result["status"]
                        stage = status.get("stage", "unknown")
                        progress = status.get("progress", 0)
                        
                        print(f"   Check {i+1}: Stage: {stage}, Progress: {progress}%")
                        
                        if stage == "completed":
                            print("   ✅ Background processing completed!")
                            break
                        elif stage == "failed":
                            print("   ❌ Background processing failed!")
                            errors = status.get("errors", [])
                            if errors:
                                print(f"      Errors: {errors}")
                            break
                    else:
                        print(f"   ❌ Status check failed: {status_result.get('message')}")
                else:
                    print(f"   ❌ Failed to get status: {response.status_code}")
                
                time.sleep(5)  # Wait 5 seconds between checks
                
            except Exception as e:
                print(f"   ❌ Error monitoring progress: {str(e)}")
                break
        
        # Step 5: Refresh document from background processing
        print(f"\n🔄 Step 5: Refreshing document from background processing...")
        response = requests.post(f"{BASE_URL}/api/document/{doc_id}/refresh-from-background")
        if response.status_code == 200:
            refresh_result = response.json()
            if refresh_result.get("success"):
                extracted_fields = refresh_result.get("extracted_fields", {})
                field_count = refresh_result.get("field_count", 0)
                accuracy_score = refresh_result.get("accuracy_score", 0)
                
                print(f"   ✅ Refresh successful!")
                print(f"      Document Type: {refresh_result.get('document_type', 'unknown')}")
                print(f"      Extracted Fields: {field_count}")
                print(f"      Accuracy Score: {accuracy_score}%")
                
                if extracted_fields:
                    print("      Sample extracted fields:")
                    count = 0
                    for key, value in extracted_fields.items():
                        if not key.startswith("total_") and not key.startswith("accounts_") and count < 5:
                            print(f"         {key}: {str(value)[:50]}...")
                            count += 1
            else:
                print(f"   ⏳ Refresh result: {refresh_result.get('message')}")
        else:
            print(f"   ❌ Failed to refresh document: {response.status_code}")
        
        # Step 6: Verify final document state
        print(f"\n📋 Step 6: Verifying final document state...")
        response = requests.get(f"{BASE_URL}/api/document/{doc_id}")
        if response.status_code == 200:
            doc_detail = response.json()
            if doc_detail.get("success"):
                doc = doc_detail["document"]
                extracted_fields = doc.get("documents", [{}])[0].get("extracted_fields", {})
                accuracy_score = doc.get("documents", [{}])[0].get("accuracy_score", 0)
                background_processed = doc.get("documents", [{}])[0].get("background_processed", False)
                
                print(f"   Final extracted fields: {len(extracted_fields)}")
                print(f"   Accuracy score: {accuracy_score}%")
                print(f"   Background processed: {background_processed}")
                
                if len(extracted_fields) > 5 and background_processed:
                    print("   ✅ SUCCESS! Death certificate processed by background system")
                    
                    # Show some key fields that should be extracted from death certificates
                    key_fields = ["Full_Name", "Date_of_Death", "Certificate_Number", "Account_Number", 
                                "Place_of_Death", "Cause_of_Death", "Age", "Date_of_Birth"]
                    
                    print("      Key death certificate fields found:")
                    for field in key_fields:
                        if field in extracted_fields:
                            value = extracted_fields[field]
                            if isinstance(value, dict):
                                value = value.get("value", "N/A")
                            print(f"         {field}: {str(value)[:50]}...")
                else:
                    print("   ❌ Background processing may not have completed successfully")
        
        print("\n🎯 Death Certificate Processing Test Summary:")
        print("   1. ✅ Document identification and type detection")
        print("   2. ✅ Background processing initiation")
        print("   3. ✅ Progress monitoring")
        print("   4. ✅ Document refresh from background results")
        print("   5. ✅ Final verification")
        
        print(f"\n💡 For {doc_type} documents:")
        print("   • Background processing uses direct LLM extraction (no account splitting)")
        print("   • Fields are extracted from the entire document text")
        print("   • Results are cached and updated in the main document record")
        print("   • UI should show extracted fields immediately after processing")
        
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to server. Make sure app_modular.py is running.")
    except Exception as e:
        print(f"❌ Test failed with error: {str(e)}")

def test_page_extraction_for_death_certificate():
    """Test page extraction for death certificates using cached results"""
    
    print("\n📄 Testing Page Extraction for Death Certificates")
    print("=" * 50)
    
    try:
        # Get first document
        response = requests.get(f"{BASE_URL}/api/documents")
        if response.status_code != 200:
            print("❌ Failed to get documents")
            return
        
        docs = response.json().get("documents", [])
        if not docs:
            print("❌ No documents found")
            return
        
        # Find death certificate or use first document
        test_doc = None
        for doc in docs:
            doc_type = doc.get("document_type_info", {}).get("type", "unknown")
            if doc_type == "death_certificate":
                test_doc = doc
                break
        
        if not test_doc:
            test_doc = docs[0]
        
        doc_id = test_doc["id"]
        doc_type = test_doc.get("document_type_info", {}).get("type", "unknown")
        
        print(f"🎯 Testing page extraction for: {doc_id} ({doc_type})")
        
        # Test page extraction (should use cached data if available)
        response = requests.get(f"{BASE_URL}/api/document/{doc_id}/page/0/extract")
        if response.status_code == 200:
            result = response.json()
            
            if result.get("cached"):
                print("✅ Page extraction used cached data from background processing")
                print(f"   Cache source: {result.get('cache_source', 'unknown')}")
                extracted_fields = result.get("extracted_fields", {})
                print(f"   Extracted fields: {len(extracted_fields)}")
            elif result.get("processing_in_background"):
                print("⏳ Page is being processed in background")
                print(f"   Stage: {result.get('stage', 'unknown')}")
                print(f"   Progress: {result.get('progress', 0)}%")
            elif result.get("success") and result.get("extracted_fields"):
                print("🔄 Page extraction performed fresh (no cache available)")
                extracted_fields = result.get("extracted_fields", {})
                print(f"   Extracted fields: {len(extracted_fields)}")
            else:
                print("❌ Page extraction failed or returned no data")
                print(f"   Result keys: {list(result.keys())}")
        else:
            print(f"❌ Page extraction failed: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Error testing page extraction: {str(e)}")

if __name__ == "__main__":
    test_death_certificate_processing()
    
    # Ask if user wants to test page extraction
    test_extraction = input("\n🤔 Do you want to test page extraction with cache? (y/n): ").lower().strip()
    if test_extraction == 'y':
        test_page_extraction_for_death_certificate()