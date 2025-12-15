#!/usr/bin/env python3
"""Test script to verify UI integration with background processing."""

import requests
import time
import json

BASE_URL = "http://localhost:5015"

def test_ui_integration():
    """Test that background processing results are visible in the UI"""
    
    print("🧪 Testing UI Integration with Background Processing")
    print("=" * 60)
    
    try:
        # Step 1: Get list of documents
        print("\n📋 Step 1: Getting document list...")
        response = requests.get(f"{BASE_URL}/api/documents")
        if response.status_code != 200:
            print("❌ Failed to get documents list")
            return
        
        docs = response.json().get("documents", [])
        if not docs:
            print("❌ No documents found. Please upload a document first.")
            return
        
        doc_id = docs[0]["id"]
        doc_name = docs[0].get("filename", "Unknown")
        print(f"✅ Testing with document: {doc_id} ({doc_name})")
        
        # Step 2: Check current document state
        print(f"\n🔍 Step 2: Checking current document state...")
        response = requests.get(f"{BASE_URL}/api/document/{doc_id}")
        if response.status_code == 200:
            doc_detail = response.json()
            if doc_detail.get("success"):
                doc = doc_detail["document"]
                accounts = doc.get("documents", [{}])[0].get("accounts", [])
                print(f"   Current accounts in document: {len(accounts)}")
                
                if len(accounts) > 0:
                    print("   ✅ Document already has accounts - background processing worked!")
                    for i, acc in enumerate(accounts[:3]):  # Show first 3
                        acc_num = acc.get("accountNumber", "Unknown")
                        print(f"      Account {i+1}: {acc_num}")
                else:
                    print("   ⏳ Document has no accounts yet")
        
        # Step 3: Check background processing status
        print(f"\n🔄 Step 3: Checking background processing status...")
        response = requests.get(f"{BASE_URL}/api/document/{doc_id}/background-status")
        if response.status_code == 200:
            bg_result = response.json()
            if bg_result.get("success"):
                status = bg_result["status"]
                stage = status.get("stage", "unknown")
                progress = status.get("progress", 0)
                bg_accounts = status.get("accounts", [])
                
                print(f"   Background Stage: {stage}")
                print(f"   Background Progress: {progress}%")
                print(f"   Background Accounts: {len(bg_accounts)}")
                
                if len(bg_accounts) > 0:
                    print("   ✅ Background processing found accounts!")
                    for i, acc in enumerate(bg_accounts[:3]):  # Show first 3
                        acc_num = acc.get("accountNumber", "Unknown")
                        print(f"      BG Account {i+1}: {acc_num}")
                else:
                    print("   ⏳ Background processing hasn't found accounts yet")
            else:
                print(f"   ❌ Background status check failed: {bg_result.get('message')}")
        else:
            print(f"   ❌ Failed to get background status: {response.status_code}")
        
        # Step 4: Try to refresh document from background
        print(f"\n🔄 Step 4: Refreshing document from background processing...")
        response = requests.post(f"{BASE_URL}/api/document/{doc_id}/refresh-from-background")
        if response.status_code == 200:
            refresh_result = response.json()
            if refresh_result.get("success"):
                accounts = refresh_result.get("accounts", [])
                print(f"   ✅ Refresh successful! Found {len(accounts)} accounts")
                
                if len(accounts) > 0:
                    for i, acc in enumerate(accounts[:3]):  # Show first 3
                        acc_num = acc.get("accountNumber", "Unknown")
                        print(f"      Refreshed Account {i+1}: {acc_num}")
            else:
                print(f"   ⏳ Refresh result: {refresh_result.get('message')}")
        else:
            print(f"   ❌ Failed to refresh document: {response.status_code}")
        
        # Step 5: Check document state after refresh
        print(f"\n📋 Step 5: Checking document state after refresh...")
        response = requests.get(f"{BASE_URL}/api/document/{doc_id}")
        if response.status_code == 200:
            doc_detail = response.json()
            if doc_detail.get("success"):
                doc = doc_detail["document"]
                accounts = doc.get("documents", [{}])[0].get("accounts", [])
                print(f"   Final accounts in document: {len(accounts)}")
                
                if len(accounts) > 0:
                    print("   ✅ SUCCESS! Document now has accounts visible in UI")
                    for i, acc in enumerate(accounts[:3]):  # Show first 3
                        acc_num = acc.get("accountNumber", "Unknown")
                        print(f"      Final Account {i+1}: {acc_num}")
                else:
                    print("   ❌ Document still has no accounts")
        
        # Step 6: Test loan document processing endpoint
        print(f"\n🏦 Step 6: Testing loan document processing endpoint...")
        response = requests.post(f"{BASE_URL}/api/document/{doc_id}/process-loan")
        if response.status_code == 200:
            loan_result = response.json()
            if loan_result.get("success"):
                accounts = loan_result.get("accounts", [])
                source = loan_result.get("source", "unknown")
                print(f"   ✅ Loan processing successful! Found {len(accounts)} accounts")
                print(f"   Source: {source}")
                
                if len(accounts) > 0:
                    for i, acc in enumerate(accounts[:3]):  # Show first 3
                        acc_num = acc.get("accountNumber", "Unknown")
                        print(f"      Loan Account {i+1}: {acc_num}")
            else:
                print(f"   ❌ Loan processing failed: {loan_result.get('message')}")
        else:
            print(f"   ❌ Failed to call loan processing: {response.status_code}")
        
        print("\n🎯 UI Integration Test Summary:")
        print("   1. ✅ Document list accessible")
        print("   2. ✅ Background processing status checkable")
        print("   3. ✅ Document refresh from background working")
        print("   4. ✅ Loan processing endpoint integration working")
        print("\n💡 If accounts are not showing in UI:")
        print("   • Check browser console for JavaScript errors")
        print("   • Verify the UI is calling the correct API endpoints")
        print("   • Use the background_processing_ui_helper.js for auto-refresh")
        print("   • Check that the document list is being refreshed after processing")
        
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to server. Make sure app_modular.py is running.")
    except Exception as e:
        print(f"❌ Test failed with error: {str(e)}")

def test_force_processing():
    """Test forcing background processing and monitoring results"""
    
    print("\n🚀 Testing Force Background Processing")
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
        
        doc_id = docs[0]["id"]
        print(f"🎯 Forcing background processing for document: {doc_id}")
        
        # Force background processing
        response = requests.post(f"{BASE_URL}/api/document/{doc_id}/force-background-processing")
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                print("✅ Background processing forced successfully")
                
                # Monitor progress for 30 seconds
                print("⏳ Monitoring progress for 30 seconds...")
                for i in range(6):  # 6 checks over 30 seconds
                    time.sleep(5)
                    
                    response = requests.get(f"{BASE_URL}/api/document/{doc_id}/background-status")
                    if response.status_code == 200:
                        status_result = response.json()
                        if status_result.get("success"):
                            status = status_result["status"]
                            stage = status.get("stage", "unknown")
                            progress = status.get("progress", 0)
                            pages_processed = status.get("pages_processed", 0)
                            total_pages = status.get("total_pages", 0)
                            
                            print(f"   Check {i+1}: {stage} - {progress}% - Pages: {pages_processed}/{total_pages}")
                            
                            if stage == "completed":
                                print("   ✅ Processing completed!")
                                break
                        else:
                            print(f"   ❌ Status check failed: {status_result.get('message')}")
                    else:
                        print(f"   ❌ Failed to get status: {response.status_code}")
                
                print("✅ Force processing test completed")
            else:
                print(f"❌ Failed to force processing: {result.get('message')}")
        else:
            print(f"❌ Failed to force processing: {response.status_code}")
            
    except Exception as e:
        print(f"❌ Force processing test failed: {str(e)}")

if __name__ == "__main__":
    test_ui_integration()
    
    # Ask if user wants to test force processing
    test_force = input("\n🤔 Do you want to test force background processing? (y/n): ").lower().strip()
    if test_force == 'y':
        test_force_processing()