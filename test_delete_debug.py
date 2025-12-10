#!/usr/bin/env python3
"""
Test script to debug the delete functionality
"""
import requests
import json

# Test the delete functionality
def test_delete():
    base_url = "http://localhost:5015"
    
    # First, get the current documents
    print("=== Getting current documents ===")
    response = requests.get(f"{base_url}/api/documents")
    if response.status_code == 200:
        data = response.json()
        documents = data.get("documents", [])
        print(f"Found {len(documents)} documents:")
        for doc in documents:
            print(f"  - ID: {doc['id']}, Name: {doc.get('document_name', 'N/A')}")
        
        if documents:
            # Try to delete the first document
            doc_to_delete = documents[0]
            doc_id = doc_to_delete['id']
            doc_name = doc_to_delete.get('document_name', 'Unknown')
            
            print(f"\n=== Attempting to delete document ===")
            print(f"Document ID: {doc_id}")
            print(f"Document Name: {doc_name}")
            
            # Call delete endpoint
            delete_response = requests.post(f"{base_url}/api/document/{doc_id}/delete")
            print(f"Delete response status: {delete_response.status_code}")
            print(f"Delete response: {delete_response.text}")
            
            # Check documents again
            print(f"\n=== Checking documents after delete ===")
            response2 = requests.get(f"{base_url}/api/documents")
            if response2.status_code == 200:
                data2 = response2.json()
                documents2 = data2.get("documents", [])
                print(f"Found {len(documents2)} documents after delete:")
                for doc in documents2:
                    print(f"  - ID: {doc['id']}, Name: {doc.get('document_name', 'N/A')}")
                
                if len(documents2) < len(documents):
                    print("✅ Delete worked - document count decreased")
                else:
                    print("❌ Delete failed - document count unchanged")
            else:
                print(f"Failed to get documents after delete: {response2.status_code}")
        else:
            print("No documents to delete")
    else:
        print(f"Failed to get documents: {response.status_code}")

if __name__ == "__main__":
    test_delete()