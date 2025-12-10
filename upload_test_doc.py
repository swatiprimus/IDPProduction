#!/usr/bin/env python3
"""
Upload a test document for testing delete functionality
"""
import requests
import os

def upload_test_document():
    url = "http://localhost:5015/process"
    
    # Create a simple test document
    test_content = """Test Document for Delete Functionality

Account Number: 999888777
Name: Test User
Date: 2025-12-10
Phone: 555-123-4567

This is a test document to verify that the delete functionality works properly.
"""
    
    # Write test file
    with open("test_delete_doc.txt", "w") as f:
        f.write(test_content)
    
    try:
        # Upload the file
        with open("test_delete_doc.txt", "rb") as f:
            files = {"file": ("test_delete_doc.txt", f, "text/plain")}
            response = requests.post(url, files=files)
        
        print(f"Upload response status: {response.status_code}")
        print(f"Upload response: {response.text}")
        
        if response.status_code == 200:
            print("✅ Test document uploaded successfully!")
        else:
            print("❌ Failed to upload test document")
            
    except Exception as e:
        print(f"❌ Error uploading: {str(e)}")
    
    finally:
        # Clean up test file
        if os.path.exists("test_delete_doc.txt"):
            os.remove("test_delete_doc.txt")

if __name__ == "__main__":
    upload_test_document()