#!/usr/bin/env python3
"""
Global Document Processing Queue
Prevents duplicate processing of documents across all upload paths
(simple_upload_app.py, skill_catalog.html, S3 fetcher)
"""

import threading
import json
import os
from datetime import datetime
from typing import Dict, Set, Optional

class DocumentProcessingQueue:
    """
    Thread-safe queue to track documents being processed
    Prevents duplicate processing across all upload paths
    """
    
    def __init__(self, queue_file: str = '.document_processing_queue.json'):
        """
        Initialize the document processing queue
        
        Args:
            queue_file: File to persist queue state
        """
        self.queue_file = queue_file
        self.lock = threading.RLock()
        self.processing_queue: Dict[str, Dict] = {}  # doc_id -> processing info
        self.completed_queue: Set[str] = set()  # doc_ids that have completed
        
        # Load existing queue from file
        self._load_queue()
        
        print(f"[QUEUE] 🚀 Document Processing Queue initialized")
        print(f"[QUEUE]    Queue file: {queue_file}")
        print(f"[QUEUE]    Processing: {len(self.processing_queue)} documents")
        print(f"[QUEUE]    Completed: {len(self.completed_queue)} documents")
    
    def _load_queue(self):
        """Load queue state from persistent file"""
        try:
            if os.path.exists(self.queue_file):
                with open(self.queue_file, 'r') as f:
                    data = json.load(f)
                    self.processing_queue = data.get('processing', {})
                    self.completed_queue = set(data.get('completed', []))
                    print(f"[QUEUE] 📂 Loaded queue from {self.queue_file}")
        except Exception as e:
            print(f"[QUEUE] ⚠️ Failed to load queue: {str(e)}")
            self.processing_queue = {}
            self.completed_queue = set()
    
    def _save_queue(self):
        """Save queue state to persistent file"""
        try:
            data = {
                'processing': self.processing_queue,
                'completed': list(self.completed_queue),
                'last_updated': datetime.now().isoformat()
            }
            with open(self.queue_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[QUEUE] ⚠️ Failed to save queue: {str(e)}")
    
    def add_to_queue(self, doc_id: str, filename: str, source: str = "unknown") -> bool:
        """
        Add document to processing queue
        
        Args:
            doc_id: Unique document ID
            filename: Document filename
            source: Where document came from (simple_upload, skill_catalog, s3_fetcher)
            
        Returns:
            True if added, False if already processing/completed
        """
        with self.lock:
            # Check if already processing
            if doc_id in self.processing_queue:
                status = self.processing_queue[doc_id].get('status', 'unknown')
                print(f"[QUEUE] ⚠️ Document {doc_id} already {status}: {filename}")
                return False
            
            # Check if already completed
            if doc_id in self.completed_queue:
                print(f"[QUEUE] ✅ Document {doc_id} already completed: {filename}")
                return False
            
            # Add to processing queue
            self.processing_queue[doc_id] = {
                'filename': filename,
                'source': source,
                'status': 'queued',
                'added_at': datetime.now().isoformat(),
                'started_at': None,
                'completed_at': None
            }
            
            self._save_queue()
            print(f"[QUEUE] ➕ Added to queue: {doc_id} ({filename}) from {source}")
            return True
    
    def mark_processing(self, doc_id: str) -> bool:
        """
        Mark document as currently processing
        
        Args:
            doc_id: Document ID
            
        Returns:
            True if marked, False if not in queue
        """
        with self.lock:
            if doc_id not in self.processing_queue:
                print(f"[QUEUE] ❌ Document {doc_id} not in queue")
                return False
            
            self.processing_queue[doc_id]['status'] = 'processing'
            self.processing_queue[doc_id]['started_at'] = datetime.now().isoformat()
            
            self._save_queue()
            print(f"[QUEUE] 🔄 Marked as processing: {doc_id}")
            return True
    
    def mark_completed(self, doc_id: str) -> bool:
        """
        Mark document as completed
        
        Args:
            doc_id: Document ID
            
        Returns:
            True if marked, False if not in queue
        """
        with self.lock:
            if doc_id not in self.processing_queue:
                print(f"[QUEUE] ❌ Document {doc_id} not in queue")
                return False
            
            self.processing_queue[doc_id]['status'] = 'completed'
            self.processing_queue[doc_id]['completed_at'] = datetime.now().isoformat()
            
            # Move to completed queue
            self.completed_queue.add(doc_id)
            del self.processing_queue[doc_id]
            
            self._save_queue()
            print(f"[QUEUE] ✅ Marked as completed: {doc_id}")
            return True
    
    def mark_failed(self, doc_id: str, error: str = None) -> bool:
        """
        Mark document as failed
        
        Args:
            doc_id: Document ID
            error: Error message
            
        Returns:
            True if marked, False if not in queue
        """
        with self.lock:
            if doc_id not in self.processing_queue:
                print(f"[QUEUE] ❌ Document {doc_id} not in queue")
                return False
            
            self.processing_queue[doc_id]['status'] = 'failed'
            self.processing_queue[doc_id]['completed_at'] = datetime.now().isoformat()
            if error:
                self.processing_queue[doc_id]['error'] = error
            
            # Move to completed queue (failed documents are also "completed")
            self.completed_queue.add(doc_id)
            del self.processing_queue[doc_id]
            
            self._save_queue()
            print(f"[QUEUE] ❌ Marked as failed: {doc_id}")
            return True
    
    def is_processing(self, doc_id: str) -> bool:
        """Check if document is currently processing"""
        with self.lock:
            return doc_id in self.processing_queue
    
    def is_completed(self, doc_id: str) -> bool:
        """Check if document has completed"""
        with self.lock:
            return doc_id in self.completed_queue
    
    def get_status(self, doc_id: str) -> Optional[str]:
        """
        Get document status
        
        Returns:
            'queued', 'processing', 'completed', 'failed', or None if not found
        """
        with self.lock:
            if doc_id in self.processing_queue:
                return self.processing_queue[doc_id].get('status', 'unknown')
            elif doc_id in self.completed_queue:
                return 'completed'
            return None
    
    def get_queue_info(self) -> Dict:
        """Get current queue information"""
        with self.lock:
            return {
                'processing_count': len(self.processing_queue),
                'completed_count': len(self.completed_queue),
                'processing_docs': list(self.processing_queue.keys()),
                'completed_docs': list(self.completed_queue)
            }
    
    def clear_completed(self):
        """Clear completed documents from queue (for cleanup)"""
        with self.lock:
            count = len(self.completed_queue)
            self.completed_queue.clear()
            self._save_queue()
            print(f"[QUEUE] 🧹 Cleared {count} completed documents")


# Global queue instance
_global_queue: Optional[DocumentProcessingQueue] = None


def get_document_queue() -> DocumentProcessingQueue:
    """Get or create the global document processing queue"""
    global _global_queue
    if _global_queue is None:
        _global_queue = DocumentProcessingQueue()
    return _global_queue


def init_document_queue():
    """Initialize the global document processing queue"""
    global _global_queue
    _global_queue = DocumentProcessingQueue()
    return _global_queue
