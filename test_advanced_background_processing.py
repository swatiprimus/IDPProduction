#!/usr/bin/env python3
"""Test script for advanced background processing functionality."""

import requests
import time
import json
from pathlib import Path

BASE_URL = "http://localhost:5015"

def test_background_processing():
    """Test the advanced background processing system"""
    
    print("🚀 Testing Advanced Background Processing System")
    print("=" * 60)
    
    # Step 1: Upload a document (this should trigger background processing)
    print("\n📤 Step 1: Uploading a test document...")
    
    # Check if we have any existing documents
    try:
        response = requests.get(f"{BASE_URL}/api/documents")
        if response.status_code == 200:
            docs = response.json().get("documents", [])
            if docs:
                doc_id = docs[0]["id"]
                print(f"✅ Using existing document: {doc_id}")
            else:
                print("❌ No documents found. Please upload a document first via the web interface.")
                return
        else:
            print("❌ Failed to get documents list")
            return
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to server. Make sure app_modular.py is running.")
        return
    
    # Step 2: Check background processing status
    print(f"\n🔍 Step 2: Checking background processing status for {doc_id}...")
    
    try:
        response = requests.get(f"{BASE_URL}/api/document/{doc_id}/background-status")
        if response.status_code == 200:
            status = response.json()
            print(f"✅ Background Status: {json.dumps(status, indent=2)}")
        else:
            print(f"❌ Failed to get background status: {response.status_code}")
    except Exception as e:
        print(f"❌ Error checking background status: {str(e)}")
    
    # Step 3: Force background processing if not already running
    print(f"\n🚀 Step 3: Force starting background processing for {doc_id}...")
    
    try:
        response = requests.post(f"{BASE_URL}/api/document/{doc_id}/force-background-processing")
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Force Processing Result: {json.dumps(result, indent=2)}")
        else:
            print(f"❌ Failed to force background processing: {response.status_code}")
    except Exception as e:
        print(f"❌ Error forcing background processing: {str(e)}")
    
    # Step 4: Monitor processing progress
    print(f"\n⏳ Step 4: Monitoring processing progress...")
    
    for i in range(10):  # Check for up to 10 iterations
        try:
            response = requests.get(f"{BASE_URL}/api/document/{doc_id}/background-status")
            if response.status_code == 200:
                status = response.json()
                if status.get("success"):
                    bg_status = status.get("status", {})
                    stage = bg_status.get("stage", "unknown")
                    progress = bg_status.get("progress", 0)
                    pages_processed = bg_status.get("pages_processed", 0)
                    total_pages = bg_status.get("total_pages", 0)
                    
                    print(f"   📊 Stage: {stage}, Progress: {progress}%, Pages: {pages_processed}/{total_pages}")
                    
                    if stage == "completed":
                        print("   ✅ Background processing completed!")
                        break
                else:
                    print(f"   ❌ Status check failed: {status.get('message')}")
            
            time.sleep(3)  # Wait 3 seconds between checks
            
        except Exception as e:
            print(f"   ❌ Error monitoring progress: {str(e)}")
            break
    
    # Step 5: Test cached page data retrieval
    print(f"\n📄 Step 5: Testing cached page data retrieval...")
    
    for page_num in range(3):  # Test first 3 pages
        try:
            response = requests.get(f"{BASE_URL}/api/document/{doc_id}/page/{page_num}/cached-data")
            if response.status_code == 200:
                result = response.json()
                if result.get("cached"):
                    print(f"   ✅ Page {page_num}: Cached data available")
                    print(f"      Account: {result.get('account_number', 'Unknown')}")
                    print(f"      Fields: {len(result.get('data', {}))}")
                elif result.get("processing"):
                    print(f"   ⏳ Page {page_num}: Still processing...")
                else:
                    print(f"   ❌ Page {page_num}: Not processed yet")
            else:
                print(f"   ❌ Page {page_num}: Failed to check cache ({response.status_code})")
        except Exception as e:
            print(f"   ❌ Page {page_num}: Error checking cache: {str(e)}")
    
    # Step 6: Test overall background processor status
    print(f"\n🖥️  Step 6: Checking overall background processor status...")
    
    try:
        response = requests.get(f"{BASE_URL}/api/background-processor/status")
        if response.status_code == 200:
            status = response.json()
            print(f"✅ Processor Status: {json.dumps(status, indent=2)}")
        else:
            print(f"❌ Failed to get processor status: {response.status_code}")
    except Exception as e:
        print(f"❌ Error checking processor status: {str(e)}")
    
    print("\n🎯 Test completed!")
    print("\n📋 Summary of Advanced Background Processing Features:")
    print("   • OCR + Account Splitting + LLM extraction runs automatically")
    print("   • Each document processes in its own thread")
    print("   • Pages are cached as they're processed")
    print("   • User gets cached results instantly when available")
    print("   • Processing continues even if user doesn't open the document")
    print("   • Real-time progress monitoring via API")

def test_page_extraction_with_cache():
    """Test page extraction that uses cached results"""
    
    print("\n🧪 Testing Page Extraction with Cache Integration")
    print("=" * 50)
    
    try:
        # Get first document
        response = requests.get(f"{BASE_URL}/api/documents")
        if response.status_code == 200:
            docs = response.json().get("documents", [])
            if docs:
                doc_id = docs[0]["id"]
                print(f"✅ Testing with document: {doc_id}")
                
                # Test page extraction (should use cache if available)
                response = requests.get(f"{BASE_URL}/api/document/{doc_id}/page/0/extract")
                if response.status_code == 200:
                    result = response.json()
                    if result.get("cached"):
                        print("✅ Page extraction used cached data from background processing")
                    elif result.get("processing_in_background"):
                        print("⏳ Page is being processed in background")
                    else:
                        print("🔄 Page extraction performed fresh (no cache available)")
                    
                    print(f"   Result keys: {list(result.keys())}")
                else:
                    print(f"❌ Page extraction failed: {response.status_code}")
            else:
                print("❌ No documents available for testing")
        else:
            print("❌ Failed to get documents")
            
    except Exception as e:
        print(f"❌ Error testing page extraction: {str(e)}")

if __name__ == "__main__":
    test_background_processing()
    
    # Ask if user wants to test page extraction
    test_extraction = input("\n🤔 Do you want to test page extraction with cache? (y/n): ").lower().strip()
    if test_extraction == 'y':
        test_page_extraction_with_cache()