#!/usr/bin/env python3
"""
Test script to verify the document processing queue works correctly
"""

import json
import os
import time
from document_queue import DocumentProcessingQueue, init_document_queue, get_document_queue

def test_basic_queue_operations():
    """Test basic queue operations"""
    print("\n" + "="*80)
    print("TEST 1: Basic Queue Operations")
    print("="*80)
    
    # Initialize queue
    queue = DocumentProcessingQueue('.test_queue.json')
    
    # Test 1: Add document to queue
    print("\n1️⃣ Adding document to queue...")
    result = queue.add_to_queue('doc_001', 'test_document.pdf', 'test_source')
    assert result == True, "Failed to add document to queue"
    print("✅ Document added successfully")
    
    # Test 2: Try to add same document again (should fail)
    print("\n2️⃣ Trying to add same document again...")
    result = queue.add_to_queue('doc_001', 'test_document.pdf', 'test_source')
    assert result == False, "Should not allow duplicate document"
    print("✅ Correctly rejected duplicate document")
    
    # Test 3: Mark as processing
    print("\n3️⃣ Marking document as processing...")
    result = queue.mark_processing('doc_001')
    assert result == True, "Failed to mark as processing"
    status = queue.get_status('doc_001')
    assert status == 'processing', f"Status should be 'processing', got '{status}'"
    print("✅ Document marked as processing")
    
    # Test 4: Mark as completed
    print("\n4️⃣ Marking document as completed...")
    result = queue.mark_completed('doc_001')
    assert result == True, "Failed to mark as completed"
    status = queue.get_status('doc_001')
    assert status == 'completed', f"Status should be 'completed', got '{status}'"
    print("✅ Document marked as completed")
    
    # Test 5: Try to add completed document again (should fail)
    print("\n5️⃣ Trying to add completed document again...")
    result = queue.add_to_queue('doc_001', 'test_document.pdf', 'test_source')
    assert result == False, "Should not allow re-processing of completed document"
    print("✅ Correctly rejected re-processing of completed document")
    
    # Clean up
    if os.path.exists('.test_queue.json'):
        os.remove('.test_queue.json')
    
    print("\n✅ TEST 1 PASSED: All basic operations work correctly\n")


def test_persistence():
    """Test that queue persists across restarts"""
    print("\n" + "="*80)
    print("TEST 2: Queue Persistence")
    print("="*80)
    
    # Create queue and add document
    print("\n1️⃣ Creating queue and adding document...")
    queue1 = DocumentProcessingQueue('.test_queue_persist.json')
    queue1.add_to_queue('doc_002', 'persistent_doc.pdf', 'test_source')
    queue1.mark_processing('doc_002')
    print("✅ Document added and marked as processing")
    
    # Verify file was created
    assert os.path.exists('.test_queue_persist.json'), "Queue file not created"
    print("✅ Queue file created")
    
    # Create new queue instance (simulating restart)
    print("\n2️⃣ Creating new queue instance (simulating restart)...")
    queue2 = DocumentProcessingQueue('.test_queue_persist.json')
    
    # Verify document is still in queue
    status = queue2.get_status('doc_002')
    assert status == 'processing', f"Document should still be 'processing', got '{status}'"
    print("✅ Document persisted across restart")
    
    # Verify we can't add it again
    result = queue2.add_to_queue('doc_002', 'persistent_doc.pdf', 'test_source')
    assert result == False, "Should not allow duplicate after restart"
    print("✅ Duplicate prevention works after restart")
    
    # Clean up
    if os.path.exists('.test_queue_persist.json'):
        os.remove('.test_queue_persist.json')
    
    print("\n✅ TEST 2 PASSED: Queue persistence works correctly\n")


def test_multiple_documents():
    """Test handling multiple documents"""
    print("\n" + "="*80)
    print("TEST 3: Multiple Documents")
    print("="*80)
    
    queue = DocumentProcessingQueue('.test_queue_multi.json')
    
    # Add multiple documents
    print("\n1️⃣ Adding multiple documents...")
    docs = [
        ('doc_101', 'file1.pdf', 'source1'),
        ('doc_102', 'file2.pdf', 'source2'),
        ('doc_103', 'file3.pdf', 'source3'),
    ]
    
    for doc_id, filename, source in docs:
        result = queue.add_to_queue(doc_id, filename, source)
        assert result == True, f"Failed to add {doc_id}"
    print(f"✅ Added {len(docs)} documents")
    
    # Mark all as processing
    print("\n2️⃣ Marking all as processing...")
    queue.mark_processing('doc_101')
    queue.mark_processing('doc_102')
    queue.mark_processing('doc_103')
    print("✅ Marked 3 documents as processing")
    
    # Mark one as completed
    print("\n3️⃣ Marking one as completed...")
    queue.mark_completed('doc_101')
    print("✅ Marked 1 document as completed")
    
    # Check queue info
    print("\n4️⃣ Checking queue info...")
    info = queue.get_queue_info()
    print(f"   Processing: {info['processing_count']}")
    print(f"   Completed: {info['completed_count']}")
    assert info['processing_count'] == 2, f"Should have 2 processing, got {info['processing_count']}"
    assert info['completed_count'] == 1, f"Should have 1 completed, got {info['completed_count']}"
    print("✅ Queue info correct")
    
    # Clean up
    if os.path.exists('.test_queue_multi.json'):
        os.remove('.test_queue_multi.json')
    
    print("\n✅ TEST 3 PASSED: Multiple document handling works correctly\n")


def test_global_queue():
    """Test global queue instance"""
    print("\n" + "="*80)
    print("TEST 4: Global Queue Instance")
    print("="*80)
    
    # Initialize global queue
    print("\n1️⃣ Initializing global queue...")
    init_document_queue()
    print("✅ Global queue initialized")
    
    # Get global queue
    print("\n2️⃣ Getting global queue instance...")
    queue = get_document_queue()
    assert queue is not None, "Failed to get global queue"
    print("✅ Got global queue instance")
    
    # Add document to global queue
    print("\n3️⃣ Adding document to global queue...")
    result = queue.add_to_queue('global_doc_001', 'global_test.pdf', 'global_source')
    assert result == True, "Failed to add to global queue"
    print("✅ Document added to global queue")
    
    # Get same global queue again
    print("\n4️⃣ Getting global queue again...")
    queue2 = get_document_queue()
    assert queue is queue2, "Should return same instance"
    print("✅ Same instance returned")
    
    # Verify document is in queue
    print("\n5️⃣ Verifying document is in queue...")
    status = queue2.get_status('global_doc_001')
    assert status == 'queued', f"Status should be 'queued', got '{status}'"
    print("✅ Document found in global queue")
    
    print("\n✅ TEST 4 PASSED: Global queue works correctly\n")


if __name__ == '__main__':
    print("\n" + "="*80)
    print("🧪 DOCUMENT QUEUE TEST SUITE")
    print("="*80)
    
    try:
        test_basic_queue_operations()
        test_persistence()
        test_multiple_documents()
        test_global_queue()
        
        print("\n" + "="*80)
        print("✅ ALL TESTS PASSED!")
        print("="*80 + "\n")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {str(e)}\n")
        exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}\n")
        import traceback
        traceback.print_exc()
        exit(1)
