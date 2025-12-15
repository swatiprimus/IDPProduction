#!/usr/bin/env python3
"""Debug the document lookup issue."""

import sys
import os
sys.path.insert(0, os.getcwd())

# Test the _get_doc function
def _get_doc(doc_id: str):
    from app import processed_documents
    print(f"Looking for doc_id: {doc_id}")
    print(f"Available documents: {len(processed_documents)}")
    for doc in processed_documents:
        print(f"  - ID: {doc['id']}, Filename: {doc['filename']}")
    return next((d for d in processed_documents if d["id"] == doc_id), None)

# Test with the current document ID
doc = _get_doc("d16e7b5aae")
print(f"Found document: {doc is not None}")
if doc:
    print(f"Document filename: {doc['filename']}")